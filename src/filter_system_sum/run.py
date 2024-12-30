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
KPI_CLASS = namedtuple("KPI", ["plant_id", "status", "eff", "prod", "cper", "soproduction", "failure", "ploss", "nominalo"]) # A data structure for kpis TODO: Erweitern um neue KPIs


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

def decision_kpi(corresponding_kpi):

    global REQUEST_LIST, PLANTS_NUMBER

    total_demand = sum(request.demand for request in REQUEST_LIST)
    plants_left = PLANTS_NUMBER
    demand_need = total_demand
    if(corresponding_kpi.soproduction > 8 or (corresponding_kpi.failure > 0.05 and corresponding_kpi.prod > 1.0)):
        if(round(total_demand/plants_left, 4) > (corresponding_kpi.nominalo * 0.8)):
            request_amount = corresponding_kpi.nominalo * 0.8
            demand_need = demand_need - request_amount
            plants_left = plants_left - 1
        else:
            request_amount = round(demand_need/plants_left, 4)
            demand_need = demand_need - request_amount
            plants_left = plants_left - 1
                
    elif(corresponding_kpi.soproduction < 2 and corresponding_kpi.ploss < 0.3 and corresponding_kpi.failure < 0.02):         #bei zu hoher production loss lohnt sich keine starke Überlast
        if(round(demand_need/plants_left, 4) > (corresponding_kpi.nominalo * 1.5)):
            request_amount = round(demand_need/plants_left, 4)
            demand_need = demand_need - request_amount
            plants_left = plants_left - 1
        else:
            request_amount = corresponding_kpi.nominalo * 1.5
            demand_need = demand_need - request_amount
            plants_left = plants_left - 1

    elif(corresponding_kpi.soproduction < 4 and corresponding_kpi.ploss < 0.1 and corresponding_kpi.failure < 0.1):
        if(round(demand_need/plants_left, 4) > (corresponding_kpi.nominalo * 1.3)):
            request_amount = round(demand_need/plants_left, 4)
            demand_need = demand_need - request_amount
            plants_left = plants_left - 1
        else:
            request_amount = corresponding_kpi.nominalo * 1.3
            demand_need = demand_need - request_amount
            plants_left = plants_left - 1
    elif(corresponding_kpi.soproduction < 6):
        if(round(demand_need/plants_left, 4) > (corresponding_kpi.nominalo * 1.1)):
            request_amount = round(demand_need/plants_left, 4)
            demand_need = demand_need - request_amount
            plants_left = plants_left - 1
        else:
            request_amount = corresponding_kpi.nominalo * 1.1
            demand_need = demand_need - request_amount
            plants_left = plants_left - 1
    else:
        if(round(demand_need/plants_left, 4) > corresponding_kpi.nominalo ):
            request_amount = round(demand_need/plants_left, 4)
            demand_need = demand_need - request_amount
            plants_left = plants_left - 1
        else:
            request_amount = corresponding_kpi.nominalo
            demand_need = demand_need - request_amount
            plants_left = plants_left - 1
    return request_amount

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
        # Place for everything that MAPE loop has to do before the iterating trough and publishing requests to filter plants
        n = 0
    else:
        online_count = sum(1 for kpi in KPI_LIST if kpi.status != "offline")

    for request_topic in TOPIC_FILTERED_WATER_REQEUST_LIST:
        # extract corresponding kpi
        request_plant_id = request_topic.split('/')[-1]
        corresponding_kpi = next((kpi for kpi in KPI_LIST if kpi.plant_id == request_plant_id), None)
        logging.debug(f"Plant id: {request_plant_id}")

        if not corresponding_kpi:
            # No kpi corresponding for plant id in the request 
            logging.debug(f"Filter plant with id {request_plant_id} and request topic: {request_topic} has no corresponding KPI.")
            request_amount = 0
        elif corresponding_kpi.status == "offline" :
            # Offline plants receive 0 allocation
            logging.debug(f"Filter plant with id {corresponding_kpi.plant_id} is offline.")
            request_amount = 0
        else:
            # Calculate allocation for active plants
            if ADAPTABLE:
                request_amount = decision_kpi(corresponding_kpi)
            else:
                request_amount = round(total_demand/online_count, 4)
            
        # Send the water production request message
        send_msg(
            client=client,
            topic=request_topic,
            timestamp=TIMESTAMP,
            amount=request_amount
        )
        logging.debug(f"Sending filtered water request message to filter plant with id {request_plant_id}: timestamp: {TIMESTAMP}, msg topic: {request_topic}, requested amount: {request_amount}")

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

def add_kpi(plant_id, status, eff, prod, cper, soproduction, failure, ploss, nominalo):
    global RECEIVED_KPI, KPI_LIST, KPI_CLASS

    KPI_LIST.append(KPI_CLASS(plant_id, status, eff, prod, cper, soproduction, failure, ploss, nominalo))
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
    eff = payload["eff"]
    prod = payload["prod"]
    cper = payload["cper"]
    soproduction = payload["soproduction"]
    failure = payload["failure"]
    ploss = payload["ploss"]
    nominalo = payload["nominalo"]
    logging.debug(f"Received message with KPI: timestamp. {timestamp}, msg topic: {msg.topic}, plant_id: {plant_id}, status: {status}, eff: {eff}, prod: {prod}, cper: {cper}, soproduction: {soproduction}, failure: {failure}, ploss: {ploss}, nominalo: {nominalo}")
    
    add_kpi(plant_id, status, eff, prod, cper, soproduction, failure, ploss, nominalo)
    
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
    logging.info(f"Received message with to change mode, adaptable mode is {ADAPTABLE}")

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

