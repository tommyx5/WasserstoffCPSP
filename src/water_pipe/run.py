import sys
import json
import logging
from mqtt.mqtt_wrapper import MQTTWrapper
import math
import os
from collections import namedtuple

def getenv_or_exit(env_name, default="default"):
    value = os.getenv(env_name, default)
    if value == default:
        raise SystemExit(f"Environment variable {env_name} not set")
    return value

TICK = getenv_or_exit('TOPIC_TICK_GEN_TICK', 'default')
TOPIC_REQUEST = getenv_or_exit('TOPIC_WATER_PIPE_WATER_REQUEST', "default") # Topic to request water from water pipe with

WATER_SUPPLY = float(getenv_or_exit('WATER_PIPE_SUPPLY', 0.0)) # Water volume (in m^3) that can be supplied by the pipe
PLANTS_NUMBER = int(getenv_or_exit('NUMBER_OF_FILTER_PLANTS', 0))

TIMESTAMP = 0
AVAILABLE_WATER = 0 # total volume of water that can be supplied
RECEIVED_REQUESTS = 0

REQUEST_LIST = [] # A list to hold all requests
REQUEST_CLASS = namedtuple("Request", ["plant_id", "reply_topic", "demand"]) # A data structure for requests

def send_reply_msg(client, reply_topic, timestamp, amount):
    data = {
        "timestamp": timestamp,  
        "amount": amount
    }
    client.publish(reply_topic, json.dumps(data))

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

    if not REQUEST_LIST:
        print("No requests to process.")
        return

    # Calculate the total demand
    total_demand = sum(request.demand for request in REQUEST_LIST)

    # Use the supplied supply function to calculate allocation
    allocation = supply_function(AVAILABLE_WATER, total_demand, REQUEST_LIST)

    # Publish replies (simulate publishing with print statements for now)
    for request in REQUEST_LIST:
        supply = allocation.get(request.plant_id, 0)

        send_reply_msg(client, request.reply_topic, TIMESTAMP, supply)

    # Clear the REQUESTS list after processing
    REQUEST_LIST.clear()
    RECEIVED_REQUESTS = 0

def add_request(plant_id, reply_topic, demand):
    global RECEIVED_REQUESTS, REQUEST_LIST, REQUEST_CLASS

    REQUEST_LIST.append(REQUEST_CLASS(plant_id, reply_topic, demand))
    RECEIVED_REQUESTS += 1

def on_message_tick(client, userdata, msg):
    global TIMESTAMP, WATER_SUPPLY, AVAILABLE_WATER, RECEIVED_REQUESTS
     
    TIMESTAMP = msg.payload.decode("utf-8") # extract the timestamp 
    AVAILABLE_WATER = WATER_SUPPLY # update available water
    RECEIVED_REQUESTS = 0 # update reqeust number

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

def main():
    """
    Main function to initialize the MQTT client, set up subscriptions, 
    and start the message loop.
    """
    
    # Initialize the MQTT client and connect to the broker
    mqtt = MQTTWrapper('mqttbroker', 1883, name='water_pipe')
    
    mqtt.subscribe(TICK)
    mqtt.subscribe(TOPIC_REQUEST)
    mqtt.subscribe_with_callback(TICK, on_message_tick)
    mqtt.subscribe_with_callback(TOPIC_REQUEST, on_message_request)
    
    try:
        # Start the MQTT loop to process incoming and outgoing messages
        while True:
            if RECEIVED_REQUESTS >= PLANTS_NUMBER:
                calculate_and_publish_replies(mqtt)
            
            mqtt.loop(0.05) # loop every 50ms
    except (KeyboardInterrupt, SystemExit):
        # Gracefully stop the MQTT client and exit the program on interrupt
        mqtt.stop()
        sys.exit("KeyboardInterrupt -- shutdown gracefully.")

if __name__ == '__main__':
    # Entry point for the script
    main()
