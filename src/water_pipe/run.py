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

# topic for receiving tick messages
TICK = getenv_or_exit('TOPIC_TICK_GEN_TICK', 'default')
# topic for publishing water volume
TOPIC_WATER = getenv_or_exit('TOPIC_WATER_PIPE_SUPPLY', "default")
# Water volume (in m^3) supplied by the pipe
WATER_VOLUME = float(getenv_or_exit('WATER_PIPE_SUPPLY', 0.0))

def on_message_tick(client, userdata, msg):
    """
    Callback function that processes messages from the tick generator topic.
    It publishes the volume of water that can be supplied by the pipe
    
    Parameters:
    client (MQTT client): The MQTT client instance
    userdata: User-defined data (not used here)
    msg (MQTTMessage): The message containing the tick timestamp
    """
    global WATER_VOLUME
    global TOPIC_WATER
    
     
    #extracting the timestamp 
    timestamp = msg.payload.decode("utf-8")

    #creating the new data
    data = {
        "water_volume": WATER_VOLUME,  # Ensure this is a float, which is JSON serializable
        "timestamp": timestamp
    }
    
    client.publish(TOPIC_WATER, json.dumps(data))

def main():
    """
    Main function to initialize the MQTT client, set up subscriptions, 
    and start the message loop.
    """
    
    # Initialize the MQTT client and connect to the broker
    mqtt = MQTTWrapper('mqttbroker', 1883, name='water_pipe')
    
    # Subscribe to the tick topic
    mqtt.subscribe(TICK)
    # Subscribe with a callback function to handle incoming tick messages
    mqtt.subscribe_with_callback(TICK, on_message_tick)
    
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
