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

TICK = getenv_or_exit('TOPIC_TICK_GEN_TICK', 'default')
TOPIC_WATER = getenv_or_exit('TOPIC_WATER_PIPE_SUPPLY', "default")
TOPIC_REQUEST = getenv_or_exit('TOPIC_WATER_PIPE_WATER_REQUEST', "default")

# Water volume (in m^3) that can be supplied by the pipe
WATER = float(getenv_or_exit('WATER_PIPE_SUPPLY', 0.0))

available_water = 0 # total volume of water that can be supplied

def on_message_tick(client, userdata, msg):
    """
    Callback function that processes messages from the tick generator topic.
    It publishes the volume of water that can be supplied by the pipe
    
    Parameters:
    client (MQTT client): The MQTT client instance
    msg (MQTTMessage): The message containing the tick timestamp
    """
    global WATER, TOPIC_WATER, available_water
     
    #extracting the timestamp 
    timestamp = msg.payload.decode("utf-8")

    available_water = WATER # update available water

    data = {
        "watersupply": available_water,  # Ensure this is a float, which is JSON serializable
        "timestamp": timestamp
    }
    
    client.publish(TOPIC_WATER, json.dumps(data))

def calculate_supply(demand):
    global available_water

    water_supplied = 0
    if(demand < available_water):
        water_supplied = demand
        available_water = available_water - demand
    else:
        water_supplied = available_water
        available_water = 0
    return water_supplied

def on_message_request(client, userdata, msg):
    """
    Callback function that processes messages from the request topic.
    It publishes the volume of water that can be supplied by the pipe
    
    Parameters:
    client (MQTT client): The MQTT client instance
    msg (MQTTMessage): The message containing the tick timestamp
    """
    
    #extracting the timestamp and other data
    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    topic = payload["topic"] # topic to publish the supplied water to
    demand = payload["waterdemand"]

    water_suplied = calculate_supply(demand)
    
    data = {
        "watersupply": water_suplied, 
        "timestamp": timestamp
    }

    client.publish(topic, json.dumps(data))

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
        mqtt.loop_forever()
    except (KeyboardInterrupt, SystemExit):
        # Gracefully stop the MQTT client and exit the program on interrupt
        mqtt.stop()
        sys.exit("KeyboardInterrupt -- shutdown gracefully.")

if __name__ == '__main__':
    # Entry point for the script
    main()
