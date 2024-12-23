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
TOPIC_ADAPTIVE_MODE = getenv_or_exit('TOPIC_ADAPTIVE_MODE', 'default')

TOPIC_SUPPLY_LIST = []
TOPIC_KPI_LIST = []
TOPIC_FILTERED_WATER_REQEUST_LIST = []
for i in range(PLANTS_NUMBER):
    TOPIC_FILTERED_WATER_REQEUST_LIST.append(TOPIC_FILTERED_WATER_REQEUST+str(i))
    TOPIC_SUPPLY_LIST.append(TOPIC_SUPPLY+str(i)) # list with all supply topics
    TOPIC_KPI_LIST.append(TOPIC_KPI+str(i)) # list with all kpi topics

ADAPTABLE = False

TIMESTAMP = 0
AVAILABLE_WATER = 0 # total volume of water that can be supplied
RECEIVED_REQUESTS = 0
RECEIVED_SUPPLIES = 0
RECEIVED_KPI = 0

TOTAL_PLANED_PER_TICK = 0 # The total amount of filtered water planed for the next tick
TOTAL_PLANED = 0 # The total amount of filtered water planed for the day
TOTAL_PRODUCED = 0 # The total amount of water already produced during current day
TICK_COUNT = 0

REQUEST_LIST = [] # A list to hold all requests
SUPPLY_LIST = [] # A list to hold all supplies
KPI_LIST = [] # A list to hold all kpis

REQUEST_CLASS = namedtuple("Request", ["plant_id", "reply_topic", "demand"]) # A data structure for requests
SUPPLY_CLASS = namedtuple("Supply", ["supply"]) # A data structure for supplies
KPI_CLASS = namedtuple("KPI", ["plant_id", "status", "eff", "prod", "cper"]) # A data structure for kpis

TOPIC_FILTER_SYSTEM_SUM_DATA = getenv_or_exit("TOPIC_FILTER_SUM_FILTER_SUM_DATA", "default")

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
    global AVAILABLE_WATER, SUPPLY_LIST, RECEIVED_SUPPLIES, TOTAL_PRODUCED

    # Calculate the total supply
    AVAILABLE_WATER = sum(supply.supply for supply in SUPPLY_LIST)
    TOTAL_PRODUCED += AVAILABLE_WATER


    # Publish the data for the dashboard
    # Maybe delete later
    global TIMESTAMP, TOPIC_FILTER_SYSTEM_SUM_DATA, TICK_COUNT
    if TICK_COUNT == 0: tick = 1 
    else: tick = TICK_COUNT
    data = {"fwater": TOTAL_PRODUCED, "mean_fwater": round(TOTAL_PRODUCED/tick,2), "timestamp": TIMESTAMP}
    client.publish(TOPIC_FILTER_SYSTEM_SUM_DATA, json.dumps(data))


    SUPPLY_LIST.clear()
    RECEIVED_SUPPLIES = 0

def weighted_coefficient_function(kpi):
    """
    Replaceable function to calculate the coefficient for allocation.
    Uses `eff`, `prod`, and `cper` as weights.
    """
    eff_weight = 0.5
    prod_weight = 0.3
    cper_weight = 0.2

    coefficient = (
        1.0 +
        kpi.eff * eff_weight +
        kpi.prod * prod_weight +
        kpi.cper * cper_weight
    )
    return max(coefficient, 0.0)  # Avoid negative coefficients

def calculate_and_publish_filtered_water_requests(client, coefficient_function=weighted_coefficient_function):
    global TIMESTAMP, REQUEST_LIST, ADAPTABLE, PLANTS_NUMBER, TOPIC_FILTERED_WATER_REQEUST_LIST, RECEIVED_REQUESTS
    global KPI_LIST, RECEIVED_KPI

    if not REQUEST_LIST:
        logging.warning("No requests to process.")
        return
    #logging.debug(f"Request list at requests distribution: {REQUEST_LIST}")

    total_demand = sum(request.demand for request in REQUEST_LIST)

    # Handling for the initial loop where no kpi is present
    if not KPI_LIST:
        logging.debug("Warning. No kpi list. Using default mean allocation")
        for request_topic in TOPIC_FILTERED_WATER_REQEUST_LIST:
            request_amount = round(total_demand/PLANTS_NUMBER, 4)
                
            # Send the water production request message
            send_msg(
                client=client,
                topic=request_topic,
                timestamp=TIMESTAMP,
                amount=request_amount
            )
            logging.debug(f"Sending request filtered water message to filter plant: timestamp: {TIMESTAMP}, topic: {request_topic}, request_amount: {request_amount}")

        RECEIVED_REQUESTS = 0
        RECEIVED_KPI = 0
        return

    if ADAPTABLE:
        # ToDo: your super mape function here
        total_coefficient = sum(coefficient_function(kpi) for kpi in KPI_LIST if kpi.status != "offline")
    else:
        online_count = sum(1 for kpi in KPI_LIST if kpi.status != "offline")

    for request_topic in TOPIC_FILTERED_WATER_REQEUST_LIST:
        # extract corresponding kpi
        request_plant_id = request_topic.split('/')[-1]
        corresponding_kpi = next((kpi for kpi in KPI_LIST if kpi.plant_id == request_plant_id), None)
        logging.debug(f"Plant id: {request_plant_id}")

        if not corresponding_kpi:
            logging.debug(f"Plant with request topic: {request_topic} has no corresponding KPI.")
            continue            

        if corresponding_kpi.status == "offline" :
            # Offline plants receive 0 allocation
            request_amount = 0
        else:
            # Calculate allocation for active plants
            if ADAPTABLE:
                # ToDo: your super mape function here
                coefficient = coefficient_function(corresponding_kpi)
                request_amount = round((coefficient/total_coefficient) * total_demand, 4)
            else:
                request_amount = round(total_demand/online_count, 4)
            
        # Send the water production request message
        send_msg(
            client=client,
            topic=request_topic,
            timestamp=TIMESTAMP,
            amount=request_amount
        )
        logging.debug(f"Sending request filtered water message to filter plant: timestamp: {TIMESTAMP}, topic: {request_topic}, request_amount: {request_amount}")

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

def add_kpi(plant_id, status, eff, prod, cper):
    global RECEIVED_KPI, KPI_LIST, KPI_CLASS

    KPI_LIST.append(KPI_CLASS(plant_id, status, eff, prod, cper))
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

    add_request(plant_id, reply_topic, demand)

    logging.debug(f"Received message with request: timestamp: {timestamp}, topic: {msg.topic}, plant_id: {plant_id}, reply_topic: {reply_topic}, demand: {demand}")

def on_message_supply(client, userdata, msg):
    """
    Callback function that processes messages from the request topic.
    """
    
    #extracting the timestamp and other data
    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    supply = payload["amount"]

    add_supply(supply)

    logging.debug(f"Received message with filtered water supply: timestamp: {timestamp}, topic: {msg.topic}, supply: {supply}")

def on_message_kpi(client, userdata, msg):
    #extracting the timestamp and other data
    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    plant_id = payload["plant_id"]
    status = payload["status"]
    eff = payload["eff"]
    prod = payload["prod"]
    cper = payload["cper"]

    add_kpi(plant_id, status, eff, prod, cper)

    logging.debug(f"Received message with KPI: timestamp: {timestamp}, topic: {msg.topic}, plant_id: {plant_id}, status: {status}, eff: {eff}, prod: {prod}, cper: {cper}")

def on_message_daily_need(client, userdata, msg):
    global TOTAL_PLANED, TOTAL_PRODUCED, TICK_COUNT
    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    TOTAL_PLANED = payload["amount"]
    TOTAL_PRODUCED = 0
    TICK_COUNT = 1

    logging.debug(f"Received message with daily request: timestamp: {timestamp}, daily demand: {TOTAL_PLANED}")

def on_message_adaptive_mode(client, userdata, msg):
    global ADAPTABLE
    boolean = msg.payload.decode("utf-8")
    if boolean == "true" or boolean == "1" or boolean == "I love Python" or boolean == "True":
        ADAPTABLE = True
    else:
        ADAPTABLE = False

    logging.debug(f"Received message with to change mode, adaptable mode is {ADAPTABLE}")

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
    mqtt.subscribe_with_callback(TICK, on_message_tick)
    mqtt.subscribe_with_callback(TOPIC_REQUEST, on_message_request)
    mqtt.subscribe_with_callback(TOPIC_ADAPTIVE_MODE, on_message_adaptive_mode)

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

