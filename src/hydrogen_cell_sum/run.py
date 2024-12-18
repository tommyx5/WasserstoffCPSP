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

TICK = getenv_or_exit('TOPIC_TICK_GEN_TICK', 'default')
HYDROGEN_REQUEST = getenv_or_exit("TOPIC_HYDROGEN_PIPE_REQUEST", "default")
HYDROGEN_SUPPLY = float(getenv_or_exit("HYDROGEN_PIPE_SUPPLY", 0.0)) # Hydrogen Volume in kg can be supplied by the pipe
PLANTS_NUMBER = int(getenv_or_exit("NUMBER_OF_HYDROGEN_PLANTS", 0))
HYDROGEN_AMOUNT = getenv_or_exit("TOPIC_HYDROGEN_PLANED_AMOUNT","default")
DAILY_HYDROGEN_AMOUNT = getenv_or_exit("TOPIC_HYDROGEN_DEMAND_GEN_HYDROGEN_DEMAND", 'default')
FILTERED_WATER_AMOUNT = getenv_or_exit("TOPIC_FILTER_PLANT_PLANED_AMOUNT", 'default')


TIMESTAMP = 0
AVAILABLE_HYDROGEN = 0 # total volume of hydrogen that can be supplied
RECEIVED_KPI_M = 0

KPIS_LIST = [] # A list to hold all requests
KPIS_CLASS = namedtuple("KPIS", ["timestamp", "plant_id", "status", "eff", "prod", "cper"]) # A data structure for requests

ADAPTIVE = False

def send_reply_msg(client, reply_topic, timestamp, amount):
    data = {
        "timestamp": timestamp,  
        "amount": amount
    }
    client.publish(reply_topic, json.dumps(data))

def weighted_supply_function(daily_goal, requests, weights=None):
    """
    Calculate supply distribution based on weighted KPIs.
    :param available_supply: Total available hydrogen supply.
    :param requests: List of KPIs.
    :param weights: Dictionary with weights for eff, prod, and cper.
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
    Calculates the supply for each requester and publishes the replies.
    """
    global KPIS_LIST, DAILY_HYDROGEN_AMOUNT, TIMESTAMP

    if not KPIS_LIST:
        print("No requests to process.")
        return

    if ADAPTIVE == True:
    # Use the supplied supply function to calculate allocation
        allocation = weighted_supply_function(DAILY_HYDROGEN_AMOUNT, KPIS_LIST)
    else:
        allocation = no_addaptive_supply_function(DAILY_HYDROGEN_AMOUNT, KPIS_LIST)
    totalsupply = 0
    # Publish replies (simulate publishing with print statements for now)
    for request in KPIS_LIST:
        
        supply = allocation.get(request.plant_id, 0)
        totalsupply += supply
        send_reply_msg(client, HYDROGEN_AMOUNT, TIMESTAMP, supply)
    
    send_reply_msg(client, FILTERED_WATER_AMOUNT, TIMESTAMP, totalsupply * 9)  # 1 kg H2O -> 9 kg H2

    # Clear the REQUESTS list after processing
    KPIS_LIST.clear()

def add_request(timestamp, plant_id, status, eff, prod, cper):
    global RECEIVED_KPI_M, KPIS_LIST, KPIS_CLASS

    KPIS_LIST.append(KPIS_CLASS(timestamp, plant_id, status, eff, prod, cper))
    RECEIVED_KPI_M += 1

def on_message_tick(client, userdata, msg):
    global TIMESTAMP, HYDROGEN_SUPPLY, AVAILABLE_HYDROGEN, RECEIVED_KPI_M
     
    TIMESTAMP = msg.payload.decode("utf-8") # extract the timestamp 
    AVAILABLE_HYDROGEN = HYDROGEN_SUPPLY # update available hydrogen
    RECEIVED_KPI_M = 0 # update request number


def on_message_request(client, userdata, msg):
    """
    Callback function that processes messages from the request topic.
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

def on_message_daily_hydrogen_amount(client, userdata, msg):
    """
    Callback function that processes messages from the daily hydrogen amount topic.
    """
    
    global DAILY_HYDROGEN_AMOUNT
    payload = json.loads(msg.payload)
    DAILY_HYDROGEN_AMOUNT = payload["hydrogen"]
    
def main():
    """
    Main function to initialize the MQTT client, set up subscriptions, 
    and start the message loop.
    """
    
    # Initialize the MQTT client and connect to the broker
    mqtt = MQTTWrapper('mqttbroker', 1883, name='hydrogen_pipe')
    

    mqtt.subscribe(TICK)
    mqtt.subscribe(HYDROGEN_REQUEST)
    mqtt.subscribe(DAILY_HYDROGEN_AMOUNT)
    mqtt.subscribe_with_callback(TICK, on_message_tick)
    mqtt.subscribe_with_callback(HYDROGEN_REQUEST, on_message_request)
    mqtt.subscribe_with_callback(DAILY_HYDROGEN_AMOUNT, on_message_daily_hydrogen_amount)

    try:
        # Start the MQTT loop to process incoming and outgoing messages
        while True:
            if RECEIVED_KPI_M >= PLANTS_NUMBER:
                
                calculate_and_publish_amount(mqtt)
                
            mqtt.loop_forever()
    except (KeyboardInterrupt, SystemExit):
        # Gracefully stop the MQTT client and exit the program on interrupt
        mqtt.stop()
        sys.exit("KeyboardInterrupt -- shutdown gracefully.")

if __name__ == '__main__':
    # Entry point for the script
    main()

