import sys
import json
import logging
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

PLANTS_NUMBER = int(getenv_or_exit("NUMBER_OF_FILTER_PLANTS", 0))

TICK = getenv_or_exit('TOPIC_TICK_GEN_TICK', 'default')
TOPIC_REQUEST = getenv_or_exit("TOPIC_FILTER_SUM_FILTERED_WATER_REQUEST", "default") # Topic to receive requests for filtered water from hydrogen plants
TOPIC_FILTERED_WATER_REQEUST = getenv_or_exit("TOPIC_FILTER_PLANT_FILTERED_WATER_REQUEST", "default") # Topic to send requests for filtered water to filter plants (must be followed by Plant ID)
TOPIC_SUPPLY = getenv_or_exit("TOPIC_FILTER_PLANT_FILTERED_WATER_SUPPLY", "default") # Base topic to receive supply msg from the filter plants (must be followed by Plant ID)
TOPIC_KPI = getenv_or_exit("TOPIC_FILTER_PLANT_KPI", "default") # Base topic to receive kpis from filter plants (must be followed by Plant ID)
TOPIC_ADAPTIVE_MODE = getenv_or_exit('TOPIC_ADAPTIVE_MODE', 'default') # Topic to change work modes 
TOPIC_FILTER_SYSTEM_SUM_DATA = getenv_or_exit("TOPIC_FILTER_SUM_FILTER_SUM_DATA", "default") # Topic to send production data for the dashboard 

TOPIC_HYDROGEN_DAILY_DEMAND = getenv_or_exit("TOPIC_HYDROGEN_DEMAND_GEN_HYDROGEN_DEMAND", 'default')

TOPIC_SUPPLY_LIST = []
TOPIC_KPI_LIST = []
TOPIC_FILTERED_WATER_REQEUST_LIST = []
for i in range(PLANTS_NUMBER):
    TOPIC_FILTERED_WATER_REQEUST_LIST.append(TOPIC_FILTERED_WATER_REQEUST+str(i))
    TOPIC_SUPPLY_LIST.append(TOPIC_SUPPLY+str(i)) # list with all supply topics
    TOPIC_KPI_LIST.append(TOPIC_KPI+str(i)) # list with all kpi topics

ADAPTABLE = False
TIMESTAMP = 0
TICK_COUNT = 0
RECEIVED_REQUESTS = 0
RECEIVED_SUPPLIES = 0
RECEIVED_KPI = 0

AVAILABLE_WATER = 0 # total volume of water that can be supplied each tick
TOTAL_FILTERED_WATER_PRODUCED = 0 # The total amount of water already produced during current day

REQUEST_LIST = [] # A list to hold all requests
SUPPLY_LIST = [] # A list to hold all supplies
KPI_LIST = [] # A list to hold all kpis

REQUEST_CLASS = namedtuple("Request", ["plant_id", "reply_topic", "demand"]) # A data structure for requests
SUPPLY_CLASS = namedtuple("Supply", ["supply"]) # A data structure for supplies
KPI_CLASS = namedtuple("KPI", ["plant_id", "status", "cper", "npower", "namount","min_output", "max_output", "pfailure", "ratio", "eff", "prod"]) # A data structure for kpis


TICKS_IN_DAY = 96

def send_msg(client, topic, timestamp, amount):
    data = {
        "timestamp": timestamp,  
        "amount": amount
    }
    client.publish(topic, json.dumps(data))

def default_supply_function(total_demand):
    """
    Default function to calculate supply distribution.
    """
    global AVAILABLE_WATER, REQUEST_LIST

    allocation = {}
    if total_demand <= AVAILABLE_WATER:
        # If total demand can be satisfied, give everyone what they requested
        for request in REQUEST_LIST:
            allocation[request.plant_id] = request.demand
            logging.debug(f"allocation for plant id: {request.plant_id} amount: {allocation[request.plant_id]}")
    else:
        # Otherwise, distribute water proportionally to demands
        for request in REQUEST_LIST:
            allocation[request.plant_id] = round(((request.demand / total_demand) * AVAILABLE_WATER), 4)  
            logging.debug(f"allocation for plant id: {request.plant_id} amount: {allocation[request.plant_id]}")
    return allocation

def calculate_and_publish_filtered_water_replies(client, supply_function=default_supply_function):
    """
    Calculates the supply for each requester and publishes the replies.
    """
    global REQUEST_LIST, RECEIVED_REQUESTS, AVAILABLE_WATER, TIMESTAMP

    # calculate the total supply from the plants
    calculate_supply(client)

    if not REQUEST_LIST:
        print("No requests to process.")
        return
    #logging.debug(f"Request list at replies distribution: {REQUEST_LIST}")

    # Calculate the total demand
    total_demand = sum(request.demand for request in REQUEST_LIST)

    # Use the supplied supply function to calculate allocation
    allocation = supply_function(total_demand)

    # Publish replies
    for request in REQUEST_LIST:
        supply = allocation.get(request.plant_id, 0)
        # send reply msg
        send_msg(
            client=client,
            topic=request.reply_topic,
            timestamp=TIMESTAMP, 
            amount=supply
        )
        logging.debug(f"Sending filtered water reply message to hydrogen plants: timestamp: {TIMESTAMP}, topic: {request.reply_topic}, request_amount: {supply}")

    # Clear the REQUESTS list after processing
    REQUEST_LIST.clear()
    RECEIVED_REQUESTS = 0

def calculate_supply(client):
    global AVAILABLE_WATER, SUPPLY_LIST, RECEIVED_SUPPLIES, TOTAL_FILTERED_WATER_PRODUCED

    # Calculate the total supply
    AVAILABLE_WATER = sum(supply.supply for supply in SUPPLY_LIST)
    TOTAL_FILTERED_WATER_PRODUCED = round(TOTAL_FILTERED_WATER_PRODUCED + AVAILABLE_WATER, 4)


    # Publish the data for the dashboard
    # Maybe delete later
    global TIMESTAMP, TOPIC_FILTER_SYSTEM_SUM_DATA, TICK_COUNT, TICKS_IN_DAY
    tick = TICK_COUNT % TICKS_IN_DAY
    if tick == 0: tick = TICKS_IN_DAY
    data = {"fwater": TOTAL_FILTERED_WATER_PRODUCED, "mean_fwater": round(TOTAL_FILTERED_WATER_PRODUCED/tick,4), "timestamp": TIMESTAMP}
    client.publish(TOPIC_FILTER_SYSTEM_SUM_DATA, json.dumps(data))


    SUPPLY_LIST.clear()
    RECEIVED_SUPPLIES = 0

"""
plantid: ID of the plant.
namount: Hydrogen output at 100% capacity.
npower: Power demand at 100% capacity.
ratio: Efficiency of resource processing.
pfailure: Possibility of failure.
status: Current status of the plant.
cper: Current performance (current_output / namount).
min_output: Hydrogen output at minimal performance.
max_output: Hydrogen output at maximal performance (including overproduction).
"""
def allocate_adaptive_production(total_demand):
    """
    Allocate filtered water production adaptively, ensuring safety limits and efficiency.
    """
    global KPI_LIST, TOPIC_FILTERED_WATER_REQEUST_LIST

    # Step 1: Get active plants
    active_plants = get_active_plants(KPI_LIST)
    if not active_plants:
        return initialize_zero_allocations(KPI_LIST)

    # Step 2: Calculate weights and precompute allocations
    precomputed_allocations = precompute_allocations(active_plants, total_demand)

    # Step 3: Adjust allocations to cap `pfailure`
    precomputed_allocations = adjust_allocations_for_safety(active_plants, precomputed_allocations)

    # Step 4: Redistribute remaining demand if needed
    precomputed_allocations = redistribute_remaining_demand(active_plants, precomputed_allocations, total_demand)

    # Step 5: Map allocations to request topics
    allocations = map_allocations_to_topics(precomputed_allocations, TOPIC_FILTERED_WATER_REQEUST_LIST)

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
    global KPI_LIST, TOPIC_FILTERED_WATER_REQEUST_LIST
    
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
    for request_topic in TOPIC_FILTERED_WATER_REQEUST_LIST:
        plant_id = request_topic.split('/')[-1]
        corresponding_kpi = next((kpi for kpi in KPI_LIST if kpi.plant_id == plant_id), None)

        if corresponding_kpi and corresponding_kpi.status != "offline":
            allocations[plant_id] = precomputed_allocations.get(corresponding_kpi.plant_id, 0)
        else:
            allocations[plant_id] = 0  # Offline or missing KPI gets zero allocation

    return allocations

def calculate_and_publish_filtered_water_requests(client):
    """
        This defenitely needs refactoring
    """
    global TIMESTAMP, REQUEST_LIST, ADAPTABLE, PLANTS_NUMBER, TOPIC_FILTERED_WATER_REQEUST_LIST, RECEIVED_REQUESTS
    global KPI_LIST, RECEIVED_KPI

    if not REQUEST_LIST:
        logging.warning("No requests to process.")
        return

    total_demand = sum(request.demand for request in REQUEST_LIST)

    # Handling for the initial loop where no kpi is present
    if not KPI_LIST:
        logging.debug("Warning. No kpi list. Using default mean allocation")
        for request_topic in TOPIC_FILTERED_WATER_REQEUST_LIST:
            allocation_for_plant = round(total_demand/PLANTS_NUMBER, 4)
                
            # Send the water production request message
            send_msg(
                client=client,
                topic=request_topic,
                timestamp=TIMESTAMP,
                amount=allocation_for_plant
            )
            logging.debug(f"Sending request filtered water message to filter plant: timestamp: {TIMESTAMP}, topic: {request_topic}, request_amount: {allocation_for_plant}")

        RECEIVED_REQUESTS = 0
        RECEIVED_KPI = 0
        return

    if ADAPTABLE:
        allocation = allocate_adaptive_production(total_demand)
    else:
        allocation = allocate_not_adaptive_production(total_demand)

    for request_topic in TOPIC_FILTERED_WATER_REQEUST_LIST:
        # extract corresponding kpi
        request_plant_id = request_topic.split('/')[-1]
        allocation_for_plant = allocation.get(request_plant_id, 0)
            
        # Send the hydrogen production request message
        send_msg(
            client=client,
            topic=request_topic,
            timestamp=TIMESTAMP,
            amount=allocation_for_plant
        )
        logging.debug(f"Sending request filtered water message to filter plant: timestamp: {TIMESTAMP}, topic: {request_topic}, request_amount: {allocation_for_plant}")

    RECEIVED_REQUESTS = 0
    RECEIVED_KPI = 0
    KPI_LIST.clear()

def add_request(plant_id, reply_topic, demand):
    global RECEIVED_REQUESTS, REQUEST_LIST, REQUEST_CLASS

    REQUEST_LIST.append(REQUEST_CLASS(plant_id, reply_topic, demand))
    RECEIVED_REQUESTS += 1

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
    global TIMESTAMP, RECEIVED_REQUESTS, RECEIVED_SUPPLIES, RECEIVED_KPI, AVAILABLE_WATER, TICK_COUNT
     
    TIMESTAMP = msg.payload.decode("utf-8") # extract the timestamp
    RECEIVED_REQUESTS = 0 # update request number
    RECEIVED_SUPPLIES = 0
    RECEIVED_KPI = 0
    AVAILABLE_WATER = 0 # reset the available water amount
    TICK_COUNT += 1
    logging.debug(f"Received tick message, timestamp: {TIMESTAMP}")

def on_message_request(client, userdata, msg):
    """
    Callback function that processes messages from the request topic.
    """
    
    #extracting the timestamp and other data
    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    plant_id = payload["plant_id"]
    reply_topic = payload["reply_topic"] # topic to publish the supplied water to
    demand = payload["amount"]
    logging.debug(f"Received message with request: timestamp: {timestamp}, topic: {msg.topic}, plant_id: {plant_id}, reply_topic: {reply_topic}, demand: {demand}")

    add_request(plant_id, reply_topic, demand)

def on_message_supply(client, userdata, msg):
    """
    Callback function that processes messages from the request topic.
    """
    #extracting the timestamp and other data
    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    supply = payload["amount"]
    logging.debug(f"Received message with filtered water supply. timestamp: {timestamp}, msg topic: {msg.topic}, supply: {supply}")

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
    
def on_message_daily_need(client, userdata, msg):
    global TOTAL_FILTERED_WATER_PRODUCED, TICK_COUNT
    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    TOTAL_FILTERED_WATER_PRODUCED = 0
    TICK_COUNT = 1
    logging.debug(f"Received message with daily request, counters reset. timestamp: {timestamp}")

def on_message_adaptive_mode(client, userdata, msg):
    global ADAPTABLE
    boolean = msg.payload.decode("utf-8")
    if boolean == "true" or boolean == "1" or boolean == "I love Python" or boolean == "True":
        ADAPTABLE = True
    else:
        ADAPTABLE = False
    logging.info(f"Received message to change mode, adaptable mode is now {ADAPTABLE}")

def main():
    """
    Main function to initialize the MQTT client, set up subscriptions, 
    and start the message loop.
    """
    
    # Initialize the MQTT client and connect to the broker
    mqtt = MQTTWrapper('mqttbroker', 1883, name='filter_system_sum')

    for topic in TOPIC_SUPPLY_LIST:
        mqtt.subscribe(topic)
        mqtt.subscribe_with_callback(topic, on_message_supply)

    for topic in TOPIC_KPI_LIST:
        mqtt.subscribe(topic)
        mqtt.subscribe_with_callback(topic, on_message_kpi)

    mqtt.subscribe(TICK)
    mqtt.subscribe(TOPIC_REQUEST)
    mqtt.subscribe(TOPIC_ADAPTIVE_MODE)
    mqtt.subscribe(TOPIC_HYDROGEN_DAILY_DEMAND)
    mqtt.subscribe_with_callback(TICK, on_message_tick)
    mqtt.subscribe_with_callback(TOPIC_REQUEST, on_message_request)
    mqtt.subscribe_with_callback(TOPIC_ADAPTIVE_MODE, on_message_adaptive_mode)
    mqtt.subscribe_with_callback(TOPIC_HYDROGEN_DAILY_DEMAND, on_message_daily_need)

    try:
        # Start the MQTT loop to process incoming and outgoing messages
        while True:
            if RECEIVED_REQUESTS >= PLANTS_NUMBER:
                calculate_and_publish_filtered_water_requests(mqtt)

            if RECEIVED_SUPPLIES >= PLANTS_NUMBER:
                calculate_and_publish_filtered_water_replies(mqtt)
            
            mqtt.loop(0.05) # loop every 50ms
    except (KeyboardInterrupt, SystemExit):
        # Gracefully stop the MQTT client and exit the program on interrupt
        mqtt.stop()
        sys.exit("KeyboardInterrupt -- shutdown gracefully.")

if __name__ == '__main__':
    # Entry point for the script
    main()

