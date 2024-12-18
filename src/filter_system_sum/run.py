import sys
import json
import logging
from random import seed, randint
from mqtt.mqtt_wrapper import MQTTWrapper
import os
from collections import namedtuple

def getenv_or_exit(env_name, default="default"):
    value = os.getenv(env_name, default)
    if value == default:
        raise SystemExit(f"Environment variable {env_name} not set")
    return value

PLANTS_NUMBER = int(getenv_or_exit("FILTER_SUM_COUNT_FILTER", 0))

TICK = getenv_or_exit('TOPIC_TICK_GEN_TICK', 'default')
TOPIC_REQUEST = getenv_or_exit("TOPIC_FILTER_SUM_FILTERED_WATER_REQUEST", "default") # Topic to receive requests for filtered water from hydrogen plants
TOPIC_FILTERED_WATER_REQEUST = getenv_or_exit("TOPIC_FILTER_PLANT_FILTERED_WATER_REQUEST", "default") # Topic to send requests for filtered water to filter plants (must be followed by Plant ID)
TOPIC_SUPPLY = getenv_or_exit("TOPIC_FILTER_PLANT_FILTERED_WATER_SUPPLY", "default") # Base topic to receive supply msg from the filter plants (must be followed by Plant ID)
TOPIC_KPI = getenv_or_exit("TOPIC_FILTER_PLANT_KPI", "default") # Base topic to receive kpis from filter plants (must be followed by Plant ID)
TOPIC_PLANED_AMOUNT = getenv_or_exit("TOPIC_FILTER_PLANT_PLANED_AMOUNT", "default") # Base topic to publish produce planed amount for the next tick (must be followed by Plant ID)

TOPIC_SUPPLY_LIST = []
TOPIC_KPI_LIST = []
TOPIC_PLANED_AMOUNT_LIST = []
TOPIC_FILTERED_WATER_REQEUST_LIST = []
for i in range(PLANTS_NUMBER):
    TOPIC_FILTERED_WATER_REQEUST_LIST.append(TOPIC_FILTERED_WATER_REQEUST+str(i))
    TOPIC_SUPPLY_LIST.append(TOPIC_SUPPLY+str(i)) # list with all supply topics
    TOPIC_KPI_LIST.append(TOPIC_KPI+str(i)) # list with all kpi topics
    TOPIC_PLANED_AMOUNT_LIST.append(TOPIC_PLANED_AMOUNT+str(i)) # list with all planed amount topics

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

TOPIC_PLANED_AMOUNT = getenv_or_exit("TOPIC_FILTER_PLANT_PLANED_AMOUNT", "default") # topic to receive produce planed amount for the next tick


def send_reply_msg(client, reply_topic, timestamp, amount):
    data = {
        "timestamp": timestamp,  
        "amount": amount
    }
    client.publish(reply_topic, json.dumps(data))

def send_supply_msg(client, supply_topic, timestamp, amount):
    data = {
        "timestamp": timestamp,  
        "amount": amount
    }
    client.publish(supply_topic, json.dumps(data))

def send_plan_msg(client, topic, timestamp, amount):
    data = {
        "timestamp": timestamp,  
        "amount": amount
    }
    client.publish(topic, json.dumps(data))

def default_supply_function(available_supply, total_demand, requests):
    """
    Default function to calculate supply distribution.
    """
    allocation = {}
    if total_demand <= available_supply:
        # If total demand can be satisfied, give everyone what they requested
        for request in requests:
            allocation[request.plant_id] = request.demand
    else:
        # Otherwise, distribute water proportionally to demands
        for request in requests:
            share = (request.demand / total_demand) * available_supply
            allocation[request.plant_id] = round(share, 2)  # Round for simplicity
    return allocation

def calculate_and_publish_replies(client, supply_function=default_supply_function):
    """
    Calculates the supply for each requester and publishes the replies.
    """
    global REQUEST_LIST, RECEIVED_REQUESTS, AVAILABLE_WATER, TIMESTAMP

    # calculate the total supply from the plants
    calculate_supply(client)

    if not REQUEST_LIST:
        print("No requests to process.")
        return

    # Calculate the total demand
    total_demand = sum(request.demand for request in REQUEST_LIST)

    # Use the supplied supply function to calculate allocation
    allocation = supply_function(AVAILABLE_WATER, total_demand, REQUEST_LIST)

    # Publish replies
    for request in REQUEST_LIST:
        supply = allocation.get(request.plant_id, 0)

        send_reply_msg(
            client=client,
            reply_topic=request.reply_topic,
            timestamp=TIMESTAMP, 
            amount=supply
        )

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
    global TIMESTAMP, TOPIC_FILTER_SYSTEM_SUM_DATA
    data = {"fwater": AVAILABLE_WATER, "mean_fwater": round(AVAILABLE_WATER/RECEIVED_SUPPLIES,2), "timestamp": TIMESTAMP}
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

"""
def calculate_and_publish_plan(client, coefficient_function=weighted_coefficient_function):
    global KPI_LIST, RECEIVED_KPI, TIMESTAMP, TOPIC_KPI_LIST, TOTAL_PLANED_PER_TICK, TOPIC_PLANED_AMOUNT_LIST
    global TOPIC_PLANED_AMOUNT 

    # Calculate how much in total needs to be done next tick
    calculate_needed_amount_per_tick()

    # Calculate total coefficients for all active plants
    total_coefficient = sum(
        coefficient_function(kpi)
        for kpi in KPI_LIST if kpi.status == "online"
    )

    # Iterate through the KPIs and send messages
    for kpi in KPI_LIST:
        # Find the topic corresponding to the plant's ID
        planed_topic = next((t for t in TOPIC_PLANED_AMOUNT_LIST if f"/{kpi.plant_id}" in t), None)
        if not planed_topic:
            print(f"No KPI topic found for filter plant ID {kpi.plant_id}, skipping...")
            continue

        if kpi.status != "online" :
            # Offline plants receive 0 allocation
            planned_amount = 0
        else:
            # Calculate allocation for active plants
            coefficient = coefficient_function(kpi)
            planned_amount = (coefficient/total_coefficient) * TOTAL_PLANED_PER_TICK

        # Send the water production plan message
        send_plan_msg(
            client=client,
            topic=planed_topic,
            timestamp=TIMESTAMP,
            amount=planned_amount
        )

    KPI_LIST.clear()
    RECEIVED_KPI = 0

def calculate_needed_amount_per_tick():
    global TOTAL_PLANED_PER_TICK, TOTAL_PRODUCED, TOTAL_PLANED, TICK_COUNT

    # avoid division by 0
    if TICK_COUNT < 96:
        plan = round((TOTAL_PLANED - TOTAL_PRODUCED) / (96-TICK_COUNT), 2)
    else:
        plan = TOTAL_PLANED - TOTAL_PRODUCED 
        print("While planing filtered water per tick, tick went to 96 and coused division by 0")

    # avoid planing negative numbers
    if(plan >= 0):
        TOTAL_PLANED_PER_TICK = plan
    else:
        print("Planed filtered water per tick can not be smaller than 0")
        TOTAL_PLANED_PER_TICK = 0
"""

def calculate_and_publish_requests(client, coefficient_function=weighted_coefficient_function):
    global TIMESTAMP, REQUEST_LIST, ADAPTABLE, PLANTS_NUMBER, TOPIC_FILTERED_WATER_REQEUST_LIST, RECEIVED_REQUESTS
    global KPI_LIST, RECEIVED_KPI

    if not REQUEST_LIST:
        print("No requests to process.")
        return

    # Calculate the total demand for this tick
    total_demand = sum(request.demand for request in REQUEST_LIST)

    if ADAPTABLE:
        print("ADAPTABLE FILTERED WATER PIPE NOT IMPLEMENTED YET")

        # If first iteration and kpi list is not there yet
        if not KPI_LIST:
            partial_demand = round (total_demand / PLANTS_NUMBER, 2)
            for request_topic in TOPIC_FILTERED_WATER_REQEUST_LIST:
                send_plan_msg(
                    client=client,
                    topic=request_topic,
                    timestamp=TIMESTAMP,
                    amount=partial_demand
                )
        else:    
            total_coefficient = sum(
                coefficient_function(kpi)
                for kpi in KPI_LIST if kpi.status == "online"
            )

            for kpi in KPI_LIST:
                # Find the topic corresponding to the plant's ID
                request_topic = next((t for t in TOPIC_FILTERED_WATER_REQEUST_LIST if f"/{kpi.plant_id}" in t), None)
                if not request_topic:
                    print(f"No request topic found for filter plant ID {kpi.plant_id}, skipping...")
                    continue

                if kpi.status != "online" :
                    # Offline plants receive 0 allocation
                    request_amount = 0
                else:
                    # Calculate allocation for active plants
                    coefficient = coefficient_function(kpi)
                    request_amount = (coefficient/total_coefficient) * total_demand

                # Send the water production request message
                send_plan_msg(
                    client=client,
                    topic=request_topic,
                    timestamp=TIMESTAMP,
                    amount=request_amount
                )
    else:
        partial_demand = round (total_demand / PLANTS_NUMBER, 2)
        for request_topic in TOPIC_FILTERED_WATER_REQEUST_LIST:
            send_plan_msg(
                client=client,
                topic=request_topic,
                timestamp=TIMESTAMP,
                amount=partial_demand
            )

    RECEIVED_REQUESTS = 0
    RECEIVED_KPI = 0
    KPI_LIST .clear()
   
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

    #Hardcode for daily messages
    global TOTAL_PRODUCED, TOTAL_PLANED
    if(TICK_COUNT % 96 == 0):
        TOTAL_PLANED = 1000
        TOTAL_PRODUCED = 0
        TICK_COUNT = 1

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

def on_message_supply(client, userdata, msg):
    """
    Callback function that processes messages from the request topic.
    """
    
    #extracting the timestamp and other data
    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    supply = payload["amount"]

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

    add_kpi(plant_id, status, eff, prod, cper)

def on_message_daily_need(client, userdata, msg):
    global TOTAL_PLANED, TOTAL_PRODUCED, TICK_COUNT
    payload = json.loads(msg.payload)
    TOTAL_PLANED = payload["amount"]
    TOTAL_PRODUCED = 0
    TICK_COUNT = 1

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
    mqtt.subscribe_with_callback(TICK, on_message_tick)
    mqtt.subscribe_with_callback(TOPIC_REQUEST, on_message_request)

    try:
        # Start the MQTT loop to process incoming and outgoing messages
        while True:
            if RECEIVED_REQUESTS >= PLANTS_NUMBER:
                calculate_and_publish_requests(mqtt)

            if RECEIVED_SUPPLIES >= PLANTS_NUMBER:
                calculate_and_publish_replies(mqtt)

            #ignore for now
            #if RECEIVED_KPI >= PLANTS_NUMBER:
                #calculate_and_publish_plan(mqtt)
            
            mqtt.loop(0.05) # loop every 50ms
    except (KeyboardInterrupt, SystemExit):
        # Gracefully stop the MQTT client and exit the program on interrupt
        mqtt.stop()
        sys.exit("KeyboardInterrupt -- shutdown gracefully.")

if __name__ == '__main__':
    # Entry point for the script
    main()

