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

PLANTS_NUMBER = int(getenv_or_exit("NUMBER_OF_HYDROGEN_PLANTS", 0))

TICK = getenv_or_exit('TOPIC_TICK_GEN_TICK', 'default')
TOPIC_HYDROGEN_DAILY_DEMAND = getenv_or_exit("TOPIC_HYDROGEN_DEMAND_GEN_HYDROGEN_DEMAND", 'default')
FILTERED_WATER_AMOUNT = getenv_or_exit("TOPIC_FILTER_PLANT_PLANED_AMOUNT", 'default')
HYDROGEN_SUPPLY_SUM = getenv_or_exit("TOPIC_HYDROGEN_SUM_DATA", 'default')
TOPIC_KPI = getenv_or_exit("TOPIC_HYDROGEN_CELL_KPI", "default") # Base topic to receive kpis from filter plants (must be followed by Plant ID)
TOPIC_ADAPTIVE_MODE = getenv_or_exit('TOPIC_ADAPTIVE_MODE', 'default')

TIMESTAMP = 0
HYDROGEN_DAILY_DEMAND = 0
HYDROGEN_PRODUCED = 0
TOTAL_HYDROGEN_PRODUCED = 0

TOPIC_SUPPLY = getenv_or_exit("TOPIC_HYDROGEN_CELL_HYDROGEN_SUPPLY", "default") # Base topic to receive supply msg from the hydrogen plants (must be followed by Plant ID)
TOPIC_HYDROGEN_REQEUST = getenv_or_exit("TOPIC_HYDROGEN_CELL_HYDROGEN_REQUEST", "default") # Topic to send requests for hydrogen to hydrogen plants (must be followed by Plant ID)

TOPIC_KPI_LIST = []
TOPIC_SUPPLY_LIST = []
TOPIC_HYDROGEN_REQEUST_LIST = []
for i in range(PLANTS_NUMBER):
    TOPIC_HYDROGEN_REQEUST_LIST.append(TOPIC_HYDROGEN_REQEUST+str(i))
    TOPIC_SUPPLY_LIST.append(TOPIC_SUPPLY+str(i)) # list with all supply topics
    TOPIC_KPI_LIST.append(TOPIC_KPI+str(i)) # list with all kpi topics

RECEIVED_KPI = 0
RECEIVED_SUPPLIES = 0

KPI_LIST = [] # A list to hold all requests
KPI_CLASS = namedtuple("KPI", ["plant_id", "status", "eff", "prod", "cper"]) # A data structure for requests
SUPPLY_LIST = [] # A list to hold all supplies
SUPPLY_CLASS = namedtuple("Supply", ["supply"]) # A data structure for supplies

ADAPTABLE = False

TICK_COUNT = 0

def send_reply_msg(client, reply_topic, timestamp, amount):
    data = {
        "timestamp": timestamp,  
        "amount": amount
    }
    client.publish(reply_topic, json.dumps(data))

def send_plan_msg(client, topic, timestamp, amount):
    data = {
        "timestamp": timestamp,  
        "amount": amount
    }
    client.publish(topic, json.dumps(data))


"""
def weighted_supply_function(daily_goal, requests, weights=None):
"""
    #Calculate supply distribution based on weighted KPIs.
    #:param available_supply: Total available hydrogen supply.
    #:param requests: List of KPIs.
    #:param weights: Dictionary with weights for eff, prod, and cper.
"""
    if weights is None:
        weights = {"eff": 0.4, "prod": 0.35, "cper": 0.25}

    # Step 1: Normalization of KPIs
    eff_values = [req.eff for req in requests]
    prod_values = [req.prod for req in requests]
    cper_values = [req.cper for req in requests]

    max_eff = max(eff_values) if eff_values else 1
    max_prod = max(prod_values) if prod_values else 1
    max_cper = max(cper_values) if cper_values else 1

    # Step 2: Calculate weighted score for each plant
    scores = {}
    for request in requests:
        normalized_eff = request.eff / max_eff
        normalized_prod = request.prod / max_prod
        normalized_cper = request.cper / max_cper

        # Weighted sum of normalized values
        score = (normalized_eff * weights["eff"] +
                 normalized_prod * weights["prod"] +
                 normalized_cper * weights["cper"])
        scores[request.plant_id] = score

    # Step 3: Proportional allocation based on scores
    total_score = sum(scores.values())
    allocation = {}
    for request in requests:
        share = (scores[request.plant_id] / total_score) * (daily_goal/24 * 4)  # 24 * 4 ticks per day
        allocation[request.plant_id] = round(share, 2)  # Round for clarity

    return allocation

def no_addaptive_supply_function(daily_goal, requests):

    allocation = {}
    amount_plants = request.len()
    for request in requests:
            allocation[request.plant_id] = (daily_goal/24 * 4) / amount_plants

    return allocation

def calculate_and_publish_amount(client):
"""
    #Calculates the supply for each requester and publishes the replies.
"""
    global KPIS_LIST, HYDROGEN_DAILY_DEMAND, TIMESTAMP, ADAPTABLE

    if not KPIS_LIST:
        print("No requests to process.")
        return

    if ADAPTABLE == True:
    # Use the supplied supply function to calculate allocation
        allocation = weighted_supply_function(HYDROGEN_DAILY_DEMAND, KPIS_LIST)
    else:
        allocation = no_addaptive_supply_function(HYDROGEN_DAILY_DEMAND, KPIS_LIST)
    totalsupply = 0
    # Publish replies (simulate publishing with print statements for now)
    for request in KPIS_LIST:
        
        supply = allocation.get(request.plant_id, 0)
        totalsupply += supply
        send_reply_msg(client, HYDROGEN_AMOUNT, TIMESTAMP, supply)
    
    send_reply_msg(client, FILTERED_WATER_AMOUNT, TIMESTAMP, totalsupply * 9)  # 1 kg H2O -> 9 kg H2
    send_reply_msg(client, HYDROGEN_SUPPLY_SUM, TIMESTAMP, totalsupply)

    # Clear the REQUESTS list after processing
    KPIS_LIST.clear()

def add_request(timestamp, plant_id, status, eff, prod, cper):
    global RECEIVED_KPI_M, KPIS_LIST, KPIS_CLASS

    KPIS_LIST.append(KPIS_CLASS(timestamp, plant_id, status, eff, prod, cper))
    RECEIVED_KPI_M += 1

def on_message_request(client, userdata, msg):
"""
    #Callback function that processes messages from the request topic.
"""
    
    #extracting the timestamp and other data
    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    plant_id = payload["plant_id"]
    status = payload["status"]
    eff = payload["eff"]
    prod = payload["prod"]
    cper = payload["cper"]

    add_request(timestamp, plant_id, status, eff, prod, cper)
"""

def on_message_tick(client, userdata, msg):
    global TIMESTAMP, RECEIVED_KPI_M
     
    TIMESTAMP = msg.payload.decode("utf-8") # extract the timestamp 
    RECEIVED_KPI_M = 0 # update request number
    calculate_and_publish_requests(client)

def on_message_daily_hydrogen_amount(client, userdata, msg):
    """
    Callback function that processes messages from the daily hydrogen amount topic.
    """
    global HYDROGEN_DAILY_DEMAND, TOTAL_HYDROGEN_PRODUCED
    payload = json.loads(msg.payload)
    HYDROGEN_DAILY_DEMAND = payload["hydrogen"]
    TOTAL_HYDROGEN_PRODUCED = 0

def calculate_hydrogen_demand_for_tick():
    global HYDROGEN_DAILY_DEMAND, TOTAL_HYDROGEN_PRODUCED, TICK_COUNT

    # avoid division by 0
    mod = TICK_COUNT % 96 
    if  mod > 0:
        plan = round((HYDROGEN_DAILY_DEMAND - TOTAL_HYDROGEN_PRODUCED) / (96-mod), 2)
    else:
        plan = HYDROGEN_DAILY_DEMAND - TOTAL_HYDROGEN_PRODUCED

    # avoid planing negative numbers
    if(plan >= 0):
        demand_for_tick = plan
    else:
        demand_for_tick = 0

    TICK_COUNT =+ 1 
    return demand_for_tick

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

def calculate_and_publish_requests(client, coefficient_function=weighted_coefficient_function):
    global TIMESTAMP, ADAPTABLE, PLANTS_NUMBER, TOPIC_HYDROGEN_REQEUST_LIST, HYDROGEN_DAILY_DEMAND, RECEIVED_KPI
    global KPI_LIST

    # Calculate the total demand for this tick
    total_demand = calculate_hydrogen_demand_for_tick()

    if ADAPTABLE:
        print("ADAPTABLE HYDROGEN PIPE NOT IMPLEMENTED YET")

        # If first iteration and kpi list is not there yet
        if not KPI_LIST:
            partial_demand = round (total_demand / PLANTS_NUMBER, 2)
            for request_topic in TOPIC_HYDROGEN_REQEUST_LIST:
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
                request_topic = next((t for t in TOPIC_HYDROGEN_REQEUST_LIST if f"/{kpi.plant_id}" in t), None)
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
        for request_topic in TOPIC_HYDROGEN_REQEUST_LIST:
            send_plan_msg(
                client=client,
                topic=request_topic,
                timestamp=TIMESTAMP,
                amount=partial_demand
            )

    RECEIVED_KPI = 0
    KPI_LIST.clear()

def calculate_supply(client):
    global HYDROGEN_PRODUCED, TOTAL_HYDROGEN_PRODUCED, SUPPLY_LIST, RECEIVED_SUPPLIES
    # Calculate the total supply
    HYDROGEN_PRODUCED = sum(supply.supply for supply in SUPPLY_LIST)
    TOTAL_HYDROGEN_PRODUCED = TOTAL_HYDROGEN_PRODUCED + HYDROGEN_PRODUCED


    # Publish the data for the dashboard
    # Maybe delete later
    global TIMESTAMP, HYDROGEN_SUPPLY_SUM, TICK_COUNT
    if TICK_COUNT == 0: tick = 1 
    else: tick = TICK_COUNT
    data = {"hydrogen": TOTAL_HYDROGEN_PRODUCED, "mean_hydrogen": round(TOTAL_HYDROGEN_PRODUCED/tick,2), "timestamp": TIMESTAMP}
    client.publish(HYDROGEN_SUPPLY_SUM, json.dumps(data))


    SUPPLY_LIST.clear()
    RECEIVED_SUPPLIES = 0

def on_message_supply(client, userdata, msg):
    """
    Callback function that processes messages from the request topic.
    """
    
    #extracting the timestamp and other data
    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    supply = payload["amount"]

    add_supply(supply)

def add_supply(supply):
    global RECEIVED_SUPPLIES, SUPPLY_LIST, SUPPLY_CLASS

    SUPPLY_LIST.append(SUPPLY_CLASS(supply))
    RECEIVED_SUPPLIES += 1

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

def add_kpi(plant_id, status, eff, prod, cper):
    global RECEIVED_KPI, KPI_LIST, KPI_CLASS

    KPI_LIST.append(KPI_CLASS(plant_id=plant_id, status=status, eff=eff, prod=prod, cper=cper))
    RECEIVED_KPI += 1

def on_message_adaptive_mode(client, userdata, msg):
    global ADAPTABLE
    boolean = msg.payload.decode("utf-8")
    if boolean == "true" or boolean == "1" or boolean == "I love Python" or boolean == "True":
        ADAPTABLE = True
    else:
        ADAPTABLE = False

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
                calculate_supply(mqtt)
                
            mqtt.loop(0.05) # loop every 50ms
    except (KeyboardInterrupt, SystemExit):
        # Gracefully stop the MQTT client and exit the program on interrupt
        mqtt.stop()
        sys.exit("KeyboardInterrupt -- shutdown gracefully.")

if __name__ == '__main__':
    # Entry point for the script
    main()