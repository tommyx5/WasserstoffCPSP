import sys
import json
import logging
from mqtt.mqtt_wrapper import MQTTWrapper
import math
import os

def getenv_or_exit(env_name, default="default"):
    value = os.getenv(env_name, default)
    if value == default:
        raise SystemExit(f"Environment variable {env_name} not set")
    return value

ID = getenv_or_exit("FILTER_PLANT_0_ID", "default")
WATER_DEMAND = float(getenv_or_exit("FILTER_PLANT_0_WATER_DEMAND", 0.0)) # in m^3
POWER_DEMAND = float(getenv_or_exit("FILTER_PLANT_0_POWER_DEMAND", 0.0)) # in kW
WATER_SUPPLY = float(getenv_or_exit("FILTER_PLANT_0_FILTERED_WATER_MAX_SUPPLY", 0.0)) # in m^3

TICK = getenv_or_exit("TOPIC_TICK_GEN_TICK", "default")
TOPIC_WATER_RECIEVE = getenv_or_exit("TOPIC_FILTER_PLANT_WATER_RECIEVE", "default")+ID # must be followed by filter plant id
TOPIC_FILTERED_WATER_SUPPLY = getenv_or_exit("TOPIC_FILTER_PLANT_FILTERED_WATER_SUPPLY", "default")+ID # must be followed by filter plant id
TOPIC_WATER_REQUEST = getenv_or_exit("TOPIC_WATER_PIPE_WATER_REQUEST", "default")

def filter_water(water_supplied):
    global WATER_DEMAND
    global WATER_SUPPLY
    
    filtered_water = 0
    if water_supplied < WATER_DEMAND:
        filtered_water = water_supplied
    else:
        filtered_water = WATER_SUPPLY
    return filtered_water

def on_message_water_received(client, userdata, msg):
    """
    Callback function that processes messages from the water received topic.
    It processes how much water is received from water pipe and generates the coresponding volume of filtered volume.
    After that publishes it along with the timestamp.
    """
    global TOPIC_FILTERED_WATER_SUPPLY

    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    water_supply = payload["watersupply"]

    filtered_water_supply = filter_water(water_supply)

    data = { 
        "filteredwatersupply": filtered_water_supply, 
        "timestamp": timestamp
    }

    # Publish the data to the topic in JSON format
    client.publish(TOPIC_FILTERED_WATER_SUPPLY, json.dumps(data))

def on_message_tick(client, userdata, msg):
    """
    Callback function that processes messages from the tick generator topic.
    It publishes topic with request for the water pipe
    
    Parameters:
    client (MQTT client): The MQTT client instance
    msg (MQTTMessage): The message containing the tick timestamp
    """
    global WATER_DEMAND
    global TOPIC_WATER_REQUEST
    global TOPIC_WATER_RECIEVE
    
    #extracting the timestamp 
    timestamp = msg.payload.decode("utf-8")

    #creating the new data
    data = {
        "topic": TOPIC_WATER_RECIEVE, # topic for water pipe to publish the reply on
        "waterdemand": WATER_DEMAND, 
        "timestamp": timestamp
    }
    
    client.publish(TOPIC_WATER_REQUEST, json.dumps(data))

def main():
    """
    Main function to initialize the MQTT client, set up subscriptions, 
    and start the message loop.
    """
    
    # Initialize the MQTT client and connect to the broker
    mqtt = MQTTWrapper('mqttbroker', 1883, name='filter_plant')
    
    mqtt.subscribe(TICK)
    mqtt.subscribe(TOPIC_WATER_RECIEVE)
    mqtt.subscribe_with_callback(TICK, on_message_tick)
    mqtt.subscribe_with_callback(TOPIC_WATER_RECIEVE, on_message_water_received)
    
    try:
        # Start the MQTT loop to process incoming and outgoing messages
        mqtt.loop_forever()
    except (KeyboardInterrupt, SystemExit):
        # Gracefully stop the MQTT client and exit the program on interrupt
        mqtt.stop()
        sys.exit("KeyboardInterrupt -- shutdown gracefully.")

if __name__ == '__main__':
    # Entry point for the script
    main()
