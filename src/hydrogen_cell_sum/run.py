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
KPI_CLASS = namedtuple("KPI", ["plant_id", "status", "eff", "prod", "cper", "soproduction", "failure", "ploss", "nominalo"]) # A data structure for requests

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

    return demand_for_tick

def decision_kpi(corresponding_kpi):

    global PLANTS_NUMBER

    total_demand = calculate_hydrogen_demand_for_tick()
    plants_left = PLANTS_NUMBER
    demand_need = total_demand
    if(corresponding_kpi.soproduction > 8 or (corresponding_kpi.failure > 0.8 and corresponding_kpi.prod > 1.0)):
        if(round(total_demand/plants_left, 4) > (corresponding_kpi.nominalo * 0.8)):
            request_amount = corresponding_kpi.nominalo * 0.8
            demand_need = demand_need - request_amount
            plants_left = plants_left - 1
        else:
            request_amount = round(demand_need/plants_left, 4)
            demand_need = demand_need - request_amount
            plants_left = plants_left - 1
                
    elif(corresponding_kpi.soproduction < 2 and corresponding_kpi.ploss < 0.3 and corresponding_kpi.failure < 0.2):         #bei zu hoher production loss lohnt sich keine starke Überlast
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
        if(round(demand_need/plants_left, 4) > corresponding_kpi.nominalo):
            request_amount = round(demand_need/plants_left, 4)
            demand_need = demand_need - request_amount
            plants_left = plants_left - 1
        else:
            request_amount = corresponding_kpi.nominalo
            demand_need = demand_need - request_amount
            plants_left = plants_left - 1
    return request_amount


def calculate_and_publish_hydrogen_requests(client):
    global TIMESTAMP, ADAPTABLE, PLANTS_NUMBER, TOPIC_HYDROGEN_REQEUST_LIST, HYDROGEN_DAILY_DEMAND, RECEIVED_KPI
    global KPI_LIST

    # Calculate the total demand for this tick
    total_demand = calculate_hydrogen_demand_for_tick()

    # Handling for the initial loop where no kpi is present
    if not KPI_LIST:
        logging.debug("Warning. No kpi list. Using default mean allocation")
        for request_topic in TOPIC_HYDROGEN_REQEUST_LIST:
            request_amount = round(total_demand/PLANTS_NUMBER, 4)
                
            # Send the water production request message
            send_msg(
                client=client,
                topic=request_topic,
                timestamp=TIMESTAMP,
                amount=request_amount
            )
            logging.debug(f"Sending  hydrogen request message to hydrogen plant. Timestamp: {TIMESTAMP}, msg topic: {request_topic}, requested amount: {request_amount}")

        RECEIVED_KPI = 0
        return

    if ADAPTABLE:
        # Place for everything that MAPE loop has to do before the iterating trough and publishing requests to filter plants
        n = 0
    else:
        online_count = sum(1 for kpi in KPI_LIST if kpi.status != "offline")

    for request_topic in TOPIC_HYDROGEN_REQEUST_LIST:
        # extract corresponding kpi
        request_plant_id = request_topic.split('/')[-1]
        corresponding_kpi = next((kpi for kpi in KPI_LIST if kpi.plant_id == request_plant_id), None)
        logging.debug(f"Plant id: {request_plant_id}")

        if not corresponding_kpi:
            # No kpi corresponding for plant id in the request 
            logging.debug(f"Hydrogen plant with id {request_plant_id} and request topic: {request_topic} has no corresponding KPI.")
            request_amount = 0
        elif corresponding_kpi.status == "offline" :
            # Offline plants receive 0 allocation
            logging.debug(f"Hydrogen plant with id {corresponding_kpi.plant_id} is offline.")
            request_amount = 0
        else:
            # Calculate allocation for active plants
            if ADAPTABLE:
                # Iterations of the MAPE loop
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
        logging.debug(f"Sending hydrogen request message to hydrogen plant with id {request_plant_id}. timestamp: {TIMESTAMP}, msg topic: {request_topic}, requested amount: {request_amount}")

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

def add_kpi(plant_id, status, eff, prod, cper, soproduction, failure, ploss, nominalo):
    global RECEIVED_KPI, KPI_LIST, KPI_CLASS

    KPI_LIST.append(KPI_CLASS(plant_id, status, eff, prod, cper, soproduction, failure, ploss, nominalo))
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
    eff = payload["eff"]
    prod = payload["prod"]
    cper = payload["cper"]
    soproduction = payload["soproduction"]
    failure = payload["failure"]
    ploss = payload["ploss"]
    nominalo = payload["nominalo"] #TODO kann raus
    logging.debug(f"Received message with KPI: timestamp. {timestamp}, msg topic: {msg.topic}, plant_id: {plant_id}, status: {status}, eff: {eff}, prod: {prod}, cper: {cper}, soproduction: {soproduction}, failure: {failure}, ploss: {ploss}, nominalo: {nominalo}")

    add_kpi(plant_id, status, eff, prod, cper, soproduction, failure, ploss, nominalo)

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