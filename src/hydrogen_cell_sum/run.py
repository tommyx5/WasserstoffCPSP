import sys
import json
import logging
import math
from random import seed, randint
from mqtt.mqtt_wrapper import MQTTWrapper
import os
from collections import namedtuple

# Configure the logger
logging.basicConfig(
    level=logging.INFO,  # Set minimum level to log
    format="%(asctime)s - %(levelname)s - %(message)s",  # Customize the output format
)

def getenv_or_exit(env_name, default="default"):
    value = os.getenv(env_name, default)
    if value == default:
        raise SystemExit(f"Environment variable {env_name} not set")
    return value

PLANTS_NUMBER = int(getenv_or_exit("NUMBER_OF_HYDROGEN_PLANTS", 0))

TICK = getenv_or_exit('TOPIC_TICK_GEN_TICK', 'default')
TOPIC_HYDROGEN_DAILY_DEMAND = getenv_or_exit("TOPIC_HYDROGEN_DEMAND_GEN_HYDROGEN_DEMAND", 'default')
TOPIC_HYDROGEN_REQEUST = getenv_or_exit("TOPIC_HYDROGEN_CELL_HYDROGEN_REQUEST", "default") # Topic to send requests for hydrogen to hydrogen plants (must be followed by Plant ID)
TOPIC_SUPPLY = getenv_or_exit("TOPIC_HYDROGEN_CELL_HYDROGEN_SUPPLY", "default") # Base topic to receive supply msg from the hydrogen plants (must be followed by Plant ID)
TOPIC_KPI = getenv_or_exit("TOPIC_HYDROGEN_CELL_KPI", "default") # Base topic to receive kpis from filter plants (must be followed by Plant ID)
TOPIC_ADAPTIVE_MODE = getenv_or_exit('TOPIC_ADAPTIVE_MODE', 'default')# Topic to change work modes 
TOPIC_HYDROGEN_SUPPLY_SUM = getenv_or_exit("TOPIC_HYDROGEN_SUM_DATA", 'default') # Topic to send production data for the dashboard

TOPIC_KPI_LIST = []
TOPIC_SUPPLY_LIST = []
TOPIC_HYDROGEN_REQEUST_LIST = []
for i in range(PLANTS_NUMBER):
    TOPIC_HYDROGEN_REQEUST_LIST.append(TOPIC_HYDROGEN_REQEUST+str(i))
    TOPIC_SUPPLY_LIST.append(TOPIC_SUPPLY+str(i)) # list with all supply topics
    TOPIC_KPI_LIST.append(TOPIC_KPI+str(i)) # list with all kpi topics

ADAPTABLE = False
TIMESTAMP = 0
TICK_COUNT = 0
RECEIVED_SUPPLIES = 0
RECEIVED_KPI = 0

HYDROGEN_DAILY_DEMAND = 0
TOTAL_HYDROGEN_PRODUCED = 0

SUPPLY_LIST = [] # A list to hold all supplies
KPI_LIST = [] # A list to hold all requests

SUPPLY_CLASS = namedtuple("Supply", ["supply"]) # A data structure for supplies
KPI_CLASS = namedtuple("KPI", ["plant_id", "status", "cper", "npower", "namount","min_output", "max_output", "pfailure", "ratio", "eff", "prod"]) # A data structure for kpis

TICKS_IN_DAY = 96

def send_msg(client, topic, timestamp, amount):
    data = {
        "timestamp": timestamp,  
        "amount": amount
    }
    client.publish(topic, json.dumps(data))

def calculate_hydrogen_demand_for_tick():
    """
    Calculate hydrogen demand for the current tick, prioritizing early production 
    using a smooth exponential distribution, while considering plant nominal output from KPI_LIST.
    """
    global HYDROGEN_DAILY_DEMAND, TOTAL_HYDROGEN_PRODUCED, TICK_COUNT, KPI_LIST

    TICKS_IN_DAY = 96
    current_tick = TICK_COUNT % TICKS_IN_DAY

    # Step 1: Get remaining ticks and avoid division by zero
    remaining_ticks = TICKS_IN_DAY - current_tick
    if remaining_ticks <= 0:
        return 0

    # Step 2: Calculate total nominal output from active plants
    if not KPI_LIST:
        total_nominal_output = 34
    else:
        total_nominal_output = sum(kpi.namount for kpi in KPI_LIST)

    # Step 3: Compute remaining demand
    remaining_demand = HYDROGEN_DAILY_DEMAND - TOTAL_HYDROGEN_PRODUCED

    # Step 4: Apply smooth exponential front-loading
    # Use a scaling factor to control the shape of the exponential curve
    scale_factor = 5  # Controls how steeply the demand tapers off
    exp_weight = math.exp(-scale_factor * current_tick / TICKS_IN_DAY)
    normalized_weight = exp_weight / math.exp(-scale_factor)  # Normalize to avoid demand overestimation

    # Calculate base demand per tick and apply weighting
    base_demand_per_tick = remaining_demand / remaining_ticks if remaining_ticks > 0 else 0
    demand_for_tick = base_demand_per_tick * normalized_weight

    # Step 5: Avoid exceeding total demand or nominal capacity
    demand_for_tick = min(demand_for_tick, remaining_demand)

    # Step 6: Log and return
    logging.debug(f"Tick: {TICK_COUNT}, Current Tick: {current_tick}, "
                  f"Demand: {demand_for_tick}, Remaining Demand: {remaining_demand}, "
                  f"Total Nominal Output: {total_nominal_output}, Normalized Weight: {normalized_weight}")
    return round(demand_for_tick, 4)

def allocate_adaptive_production(total_demand):
    """
    Allocate hydrogen production adaptively, ensuring safety limits and efficiency.
    """
    global KPI_LIST, TOPIC_HYDROGEN_REQEUST_LIST

    # Step 1: Get active plants
    active_plants = get_active_plants(KPI_LIST)
    if not active_plants:
        return initialize_zero_allocations(KPI_LIST)

    # Step 2: Calculate weights and precompute allocations
    precomputed_allocations = precompute_allocations(active_plants, total_demand)

    # Step 3: Adjust allocations based on failure possibility
    precomputed_allocations = adjust_allocations_for_safety(active_plants, precomputed_allocations)

    # Step 4: Redistribute remaining demand if needed
    precomputed_allocations = redistribute_remaining_demand(active_plants, precomputed_allocations, total_demand)

    # Step 5: Map allocations to request topics
    allocations = map_allocations_to_topics(precomputed_allocations, TOPIC_HYDROGEN_REQEUST_LIST)

    return allocations

def get_active_plants(kpi_list):
    """Filter out offline plants from the KPI list."""
    return [kpi for kpi in kpi_list if kpi.status != "offline"]

def initialize_zero_allocations(kpi_list):
    """Return zero allocations for all plants."""
    return {kpi.plant_id: 0 for kpi in kpi_list}

def calculate_total_weight(plants):
    """Calculate the total weight based on `cper` and `pfailure`."""
    return sum(
        (plant.ratio * plant.namount * plant.npower)
        #(plant.ratio * plant.namount) * plant.cper / (1 + (plant.pfailure / 100))
        for plant in plants
    )

def precompute_allocations(plants, total_demand):
    """
    Precompute allocations based on plant weights.
    Distribute equally if total weight is zero.
    """
    total_weight = calculate_total_weight(plants)

    if total_weight == 0:
        equal_allocation = round(total_demand / len(plants), 4)
        return {plant.plant_id: equal_allocation for plant in plants}

    return {
        plant.plant_id: round(
            (plant.ratio * plant.namount * plant.npower) / total_weight * total_demand, 4
            #((plant.ratio * plant.namount) * plant.cper / (1 + (plant.pfailure / 100))) / total_weight * total_demand, 4
        )
        for plant in plants
    }

def adjust_allocations_for_safety(plants, allocations):
    """
    Adjust allocations to ensure no plant exceeds the `pfailure` threshold (0.003).
    Scale down production if necessary.
    """

    for plant in plants:
        plant_id = plant.plant_id
        allocation = allocations[plant_id]

        # Determine the maximum allowable allocation to keep `pfailure` ≤ 0.003
        max_safe_allocation = calculate_safe_allocation(plant)
        max_safe_allocation = min(max_safe_allocation, plant.max_output)

        # Adjust allocation if it exceeds safety limits
        if allocation > max_safe_allocation:
            allocation = max_safe_allocation

        # Ensure allocation does not drop below the minimum output
        allocation = max(allocation, plant.min_output)

        # Update allocations and remaining demand
        allocations[plant_id] = allocation

    return allocations

def calculate_safe_allocation(plant):
    """Calculate the maximum safe allocation for a plant based on `pfailure`."""
    if plant.pfailure >= 0.002:
        return round(plant.namount * 0.99, 4) 
    else:
        return plant.max_output
    #return plant.namount * (1 - (0.003 - plant.pfailure) / 0.003)

def redistribute_remaining_demand(plants, allocations, total_demand):
    """
    Redistribute any remaining demand among plants with spare capacity.
    Only allocate to plants performing under 100% and ensure the total additional load does not exceed 100% of the remaining demand.
    """
    remaining_demand = total_demand - sum(allocations.values())
    if remaining_demand > 0:

        for plant in plants:
            plant_id = plant.plant_id
            current_load = allocations[plant_id]
            max_load = round(plant.namount * 0.99, 4)
            if current_load < max_load:  # Only redistribute to plants under 100% load
                
                additional_allocation = min(max_load-current_load, remaining_demand)

                allocations[plant_id] += additional_allocation
                remaining_demand -= additional_allocation

                # Stop redistribution if no remaining demand
                if remaining_demand <= 0:
                    break

    return allocations

def map_allocations_to_topics(precomputed_allocations, request_topics):
    """
    Map precomputed allocations to the corresponding request topics.
    """
    global KPI_LIST
    allocations = {}
    for request_topic in request_topics:
        plant_id = request_topic.split('/')[-1]
        corresponding_kpi = next((kpi for kpi in KPI_LIST if kpi.plant_id == plant_id), None)

        if corresponding_kpi and corresponding_kpi.status != "offline":
            allocations[plant_id] = precomputed_allocations.get(plant_id, 0)
        else:
            allocations[plant_id] = 0  # Offline or missing KPI gets zero allocation

    return allocations

def allocate_not_adaptive_production(total_demand):
    """
    Smarter and optimized allocation of hydrogen production based on plant characteristics.
    """
    global KPI_LIST, TOPIC_HYDROGEN_REQEUST_LIST
    
    precomputed_allocations = {}
    allocations = {}

    # Step 1: Filter active plants and calculate total weight
    active_plants = [kpi for kpi in KPI_LIST if kpi.status != "offline"]
    if not active_plants:
        precomputed_allocations = {kpi.plant_id: 0 for kpi in KPI_LIST}  # All offline, zero allocation

    total_weight = sum(plant.ratio * plant.namount for plant in active_plants)
    default_allocation = round(total_demand / len(active_plants), 4) if total_weight == 0 else None

    # Step 2: Precompute allocations based on weights or equal distribution
    precomputed_allocations = {
        plant.plant_id: round((plant.ratio * plant.namount / total_weight) * total_demand, 4)
        if total_weight > 0 else default_allocation
        for plant in active_plants
    }

    # Step 3: Assign allocations based on request topics
    for request_topic in TOPIC_HYDROGEN_REQEUST_LIST:
        plant_id = request_topic.split('/')[-1]
        corresponding_kpi = next((kpi for kpi in KPI_LIST if kpi.plant_id == plant_id), None)

        if corresponding_kpi and corresponding_kpi.status != "offline":
            allocations[plant_id] = precomputed_allocations.get(corresponding_kpi.plant_id, 0)
        else:
            allocations[plant_id] = 0  # Offline or missing KPI gets zero allocation

    return allocations

def calculate_and_publish_hydrogen_requests(client):
    global TIMESTAMP, ADAPTABLE, PLANTS_NUMBER, TOPIC_HYDROGEN_REQEUST_LIST, HYDROGEN_DAILY_DEMAND
    global KPI_LIST, RECEIVED_KPI

    # Calculate the total demand for this tick
    total_demand = calculate_hydrogen_demand_for_tick()

    # Handling for the initial loop where no kpi is present
    if not KPI_LIST:
        logging.debug("Warning. No kpi list. Using default mean allocation")
        for request_topic in TOPIC_HYDROGEN_REQEUST_LIST:
            allocation_for_plant = round(total_demand/PLANTS_NUMBER, 4)
            
            # Send the water production request message
            send_msg(
                client=client,
                topic=request_topic,
                timestamp=TIMESTAMP,
                amount=allocation_for_plant
            )
            logging.debug(f"Sending  hydrogen request message to hydrogen plant. Timestamp: {TIMESTAMP}, msg topic: {request_topic}, requested amount: {allocation_for_plant}")

        RECEIVED_KPI = 0
        return

    if ADAPTABLE:
        allocation = allocate_adaptive_production(total_demand)
    else:
        allocation = allocate_not_adaptive_production(total_demand)

    for request_topic in TOPIC_HYDROGEN_REQEUST_LIST:
        # extract corresponding topic and allocation
        request_plant_id = request_topic.split('/')[-1]
        allocation_for_plant = allocation.get(request_plant_id, 0)
            
        # Send the hydrogen production request message
        send_msg(
            client=client,
            topic=request_topic,
            timestamp=TIMESTAMP,
            amount=allocation_for_plant
        )
        logging.debug(f"Sending hydrogen request message to hydrogen plant with id {request_plant_id}. timestamp: {TIMESTAMP}, msg topic: {request_topic}, requested amount: {allocation_for_plant}")

    RECEIVED_KPI = 0
    KPI_LIST.clear()

def calculate_total_supply(client):
    global TOTAL_HYDROGEN_PRODUCED, SUPPLY_LIST, RECEIVED_SUPPLIES
    
    # Calculate the total supply
    hydrogen_produced_current_tick = sum(supply.supply for supply in SUPPLY_LIST)
    TOTAL_HYDROGEN_PRODUCED = round(TOTAL_HYDROGEN_PRODUCED + hydrogen_produced_current_tick, 4)


    # Publish the data for the dashboard
    # Maybe delete later
    global TIMESTAMP, TOPIC_HYDROGEN_SUPPLY_SUM, TICK_COUNT, TICKS_IN_DAY
    tick = TICK_COUNT % TICKS_IN_DAY
    if tick == 0: tick = TICKS_IN_DAY
    data = {"hydrogen": TOTAL_HYDROGEN_PRODUCED, "mean_hydrogen": round(TOTAL_HYDROGEN_PRODUCED/tick , 4), "timestamp": TIMESTAMP}
    client.publish(TOPIC_HYDROGEN_SUPPLY_SUM, json.dumps(data))


    SUPPLY_LIST.clear()
    RECEIVED_SUPPLIES = 0

def add_supply(supply):
    global RECEIVED_SUPPLIES, SUPPLY_LIST, SUPPLY_CLASS

    SUPPLY_LIST.append(SUPPLY_CLASS(supply))
    RECEIVED_SUPPLIES += 1

def add_kpi(plant_id, status, cper, npower, namount, min_output, max_output, pfailure, ratio, eff, prod):
    global RECEIVED_KPI, KPI_LIST, KPI_CLASS

    KPI_LIST.append(KPI_CLASS(plant_id=plant_id,
                              status=status,
                              cper=cper,
                              npower=npower,
                              namount=namount,
                              min_output=min_output,
                              max_output=max_output,
                              pfailure=pfailure,
                              ratio=ratio,
                              eff=eff,
                              prod=prod))
    RECEIVED_KPI += 1

def on_message_tick(client, userdata, msg):
    global TIMESTAMP, RECEIVED_KPI, RECEIVED_SUPPLIES, TICK_COUNT
     
    TIMESTAMP = msg.payload.decode("utf-8") # extract the timestamp
    RECEIVED_SUPPLIES = 0
    RECEIVED_KPI = 0
    TICK_COUNT += 1
    logging.debug(f"Received tick message, timestamp: {TIMESTAMP}")

    calculate_and_publish_hydrogen_requests(client)

def on_message_daily_hydrogen_amount(client, userdata, msg):
    """
    Callback function that processes messages from the daily hydrogen amount topic.
    """
    global HYDROGEN_DAILY_DEMAND, TOTAL_HYDROGEN_PRODUCED
    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    HYDROGEN_DAILY_DEMAND = payload["hydrogen"]
    TOTAL_HYDROGEN_PRODUCED = 0
    logging.debug(f"Received message with daily hydrogen request: timestamp: {timestamp}, daily demand: {HYDROGEN_DAILY_DEMAND}")

def on_message_adaptive_mode(client, userdata, msg):
    global ADAPTABLE
    boolean = msg.payload.decode("utf-8")
    if boolean == "true" or boolean == "1" or boolean == "I love Python" or boolean == "True":
        ADAPTABLE = True
    else:
        ADAPTABLE = False
    logging.info(f"Received message to change mode, adaptable mode is now {ADAPTABLE}")

def on_message_supply(client, userdata, msg):
    """
    Callback function that processes messages from the request topic.
    """
    #extracting the timestamp and other data
    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    supply = payload["amount"]
    logging.debug(f"Received message with hydrogen water supply. timestamp: {timestamp}, msg topic: {msg.topic}, supply: {supply}")

    add_supply(supply)

def on_message_kpi(client, userdata, msg):
    #extracting the timestamp and other data
    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    plant_id = payload["plant_id"]
    status = payload["status"]
    cper = payload["cper"]
    npower = payload["npower"]
    namount = payload["namount"]
    min_output = payload["min_output"]
    max_output = payload["max_output"]
    pfailure = payload["pfailure"]
    ratio = payload["ratio"]
    eff = payload["eff"]
    prod = payload["prod"]
    logging.debug(f"Received message with KPI: timestamp. {timestamp}, msg topic: {msg.topic}, plant_id: {plant_id}, status: {status}, cper: {cper}, npower: {npower}, namount: {namount}, min_output: {min_output}, max_output: {max_output}, pfailure: {pfailure}, ratio: {ratio}, eff: {eff}, prod: {prod}")
    
    add_kpi(plant_id=plant_id, status=status, cper=cper, npower=npower, namount=namount, min_output=min_output, max_output=max_output, pfailure=pfailure, ratio=ratio, eff=eff, prod=prod)
    
def main():
    """
    Main function to initialize the MQTT client, set up subscriptions, 
    and start the message loop.
    """
    
    # Initialize the MQTT client and connect to the broker
    mqtt = MQTTWrapper('mqttbroker', 1883, name='hydrogen_pipe')
    
    for topic in TOPIC_SUPPLY_LIST:
        mqtt.subscribe(topic)
        mqtt.subscribe_with_callback(topic, on_message_supply)
        
    for topic in TOPIC_KPI_LIST:
        mqtt.subscribe(topic)
        mqtt.subscribe_with_callback(topic, on_message_kpi)

    mqtt.subscribe(TICK)
    mqtt.subscribe(TOPIC_HYDROGEN_DAILY_DEMAND)
    mqtt.subscribe(TOPIC_ADAPTIVE_MODE)
    mqtt.subscribe_with_callback(TICK, on_message_tick)
    mqtt.subscribe_with_callback(TOPIC_HYDROGEN_DAILY_DEMAND, on_message_daily_hydrogen_amount)
    mqtt.subscribe_with_callback(TOPIC_ADAPTIVE_MODE, on_message_adaptive_mode)

    try:
        # Start the MQTT loop to process incoming and outgoing messages
        while True:
            if RECEIVED_SUPPLIES >= PLANTS_NUMBER:
                calculate_total_supply(mqtt)
                
            mqtt.loop(0.05) # loop every 50ms
    except (KeyboardInterrupt, SystemExit):
        # Gracefully stop the MQTT client and exit the program on interrupt
        mqtt.stop()
        sys.exit("KeyboardInterrupt -- shutdown gracefully.")

if __name__ == '__main__':
    # Entry point for the script
    main()