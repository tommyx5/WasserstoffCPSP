import sys
import json
import logging
from random import seed, randint
from mqtt.mqtt_wrapper import MQTTWrapper
import os

def getenv_or_exit(env_name, default="default"):
    value = os.getenv(env_name, default)
    if value == default:
        raise SystemExit(f"Environment variable {env_name} not set")
    return value


# MQTT topic for publishing sensor data
HYDROGEN_REQUEST = getenv_or_exit("TOPIC_HYDROGEN_DEMAND_GEN_HYDROGEN_DEMAND", "default")

# MQTT topic for receiving tick messages
TICK_TOPIC = getenv_or_exit("TOPIC_TICK_GEN_TICK", "default")

COUNT = 0
LIMIT = 24*4
L_IN_KG = 25
MAX_OUTPUT = float(getenv_or_exit("HYDROGEN_DEMAND_GEN_DAYLY_DEMAND", 0)) #kg Wasserstoff pro Tag

SEED = MAX_OUTPUT

def on_message_tick(client, userdata, msg):
    global COUNT, LIMIT,L_IN_KG, MAX_OUTPUT

    if COUNT == 0:
        hydrogen = randint(int(MAX_OUTPUT/1.25), int(MAX_OUTPUT*1.25))
        # Extract the timestamp from the tick message and decode it from UTF-8
        ts_iso = msg.payload.decode("utf-8")
        data = {"hydrogen": 2500, "timestamp": ts_iso}  #TODO hydrogen statt 5000 
        # Publish the data to the chaos sensor topic in JSON format
        client.publish(HYDROGEN_REQUEST, json.dumps(data))
    COUNT = (COUNT + 1) % LIMIT

def main():
    """
    Main function to initialize the MQTT client, set up subscriptions, 
    and start the message loop.
    """
    
    # Initialize the MQTT client and connect to the broker
    mqtt = MQTTWrapper('mqttbroker', 1883, name='request_hydrogen_gen')
    
    # Subscribe to the tick topic
    mqtt.subscribe(TICK_TOPIC)
    # Subscribe with a callback function to handle incoming tick messages
    mqtt.subscribe_with_callback(TICK_TOPIC, on_message_tick)
    
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

