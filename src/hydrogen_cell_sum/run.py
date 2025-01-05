import sys
import json
import logging
from random import seed, randint
from mqtt.mqtt_wrapper import MQTTWrapper
import os
from collections import namedtuple

# Configure the logger
logging.basicConfig(
    level=logging.DEBUG,  # Set minimum level to log
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
    global HYDROGEN_DAILY_DEMAND, TOTAL_HYDROGEN_PRODUCED, TICK_COUNT

    # avoid division by 0
    mod = TICK_COUNT % 96 
    if  mod > 0:
        plan = round((HYDROGEN_DAILY_DEMAND - TOTAL_HYDROGEN_PRODUCED) / (TICKS_IN_DAY-mod), 2)
    else:
        plan = HYDROGEN_DAILY_DEMAND - TOTAL_HYDROGEN_PRODUCED

    # avoid planing negative numbers
    if(plan >= 0):
        demand_for_tick = plan
    else:
        demand_for_tick = 0
    logging.debug(f"Total tick count: {TICK_COUNT}, current tick in day: {mod}, tick demand: {plan}")

    return demand_for_tick

def allocate_adaptive_production(total_demand):
    """
    Distributes hydrogen production demand among plants considering their KPIs,
    dynamically accounting for individual failure probabilities.
    """
    global KPI_LIST
    # Step 1: Initialize allocations
    allocations = {plant.plant_id: 0 for plant in KPI_LIST}  # Default to 0 for all plants

    # Step 2: Filter usable plants (exclude offline plants)
    usable_plants = [plant for plant in KPI_LIST if plant.status != "offline"]

    # Step 3: Prioritize plants (adjust for failure probability inversely)
    prioritized_plants = sorted(
        usable_plants,
        key=lambda p: (p.ratio, -p.cper, -1 / (p.pfailure + 1))  # Adding 1 to avoid division by zero
    )

    # Step 4: Allocate baseline workloads
    remaining_demand = total_demand

    for plant in prioritized_plants:
        # Start with the plant's minimum output allocation
        allocations[plant.plant_id] = plant.min_output
        remaining_demand = round(remaining_demand - plant.min_output, 4)

    # Step 5: Distribute remaining demand
    for plant in prioritized_plants:
        if remaining_demand <= 0:
            break

        # Calculate plant's potential contribution
        available_capacity = round(plant.namount - allocations[plant.plant_id], 4)

        # Scale contribution based on failure probability
        failure_penalty = 1 / (plant.pfailure + 1)  # Higher `pfailure` reduces capacity proportionally
        scaled_capacity = available_capacity * failure_penalty

        # Allocate capacity adjusted for failure risk
        contribution = min(remaining_demand, scaled_capacity)

        # Check if the plant can enter overproduction
        max_overproduction = plant.max_output - plant.namount
        if contribution > available_capacity:
            additional_contribution = min(remaining_demand - contribution, max_overproduction)
            contribution = round(contribution + additional_contribution, 4)

        # Update allocations and remaining resources
        allocations[plant.plant_id] += contribution
        remaining_demand -= contribution

    # Rescale if total exceeds demand (to balance errors due to floating-point arithmetic)
    total_allocated = sum(allocations.values())
    if total_allocated > total_demand:
        scaling_factor = total_demand / total_allocated
        for plant_id in allocations:
            allocations[plant_id] *= scaling_factor

    return allocations

def allocate_not_adaptive_production(total_demand):
    """
    Allocate hydrogen production based solely on the status of the plants.
    """
    # Step 1: Filter plants that are not offline
    active_plants = [kpi for kpi in KPI_LIST if kpi.status != "offline"]
    
    if not active_plants:
        # If no plants are available, return zero allocation for all
        return {kpi.plant_id: 0 for kpi in KPI_LIST}

    # Step 2: Distribute demand equally among active plants
    equal_allocation = round(total_demand / len(active_plants), 4)
    allocations = {}

    for kpi in KPI_LIST:
        if kpi.status != "offline":
            allocations[kpi.plant_id] = equal_allocation
        else:
            allocations[kpi.plant_id] = 0  # Offline plants get 0 allocation

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
        # extract corresponding kpi
        request_plant_id = request_topic.split('/')[-1]
        corresponding_kpi = next((kpi for kpi in KPI_LIST if kpi.plant_id == request_plant_id), None)
        #logging.debug(f"Plant id: {request_plant_id}")

        allocation_for_plant = allocation.get(request_plant_id, 0)

        if not corresponding_kpi:
            # No kpi corresponding for plant id in the request 
            logging.debug(f"Hydrogen plant with id {request_plant_id} and request topic: {request_topic} has no corresponding KPI.")
            
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
    logging.info(f"Received message with to change mode, adaptable mode is {ADAPTABLE}")

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