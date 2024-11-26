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
HYDROGEN_CELL_SUM_DATA = getenv_or_exit("TOPIC_HYDROGEN_CELL_SUM_HYDROGEN_CELL_SUM_DATA", "default")

# MQTT topic for receiving tick messages
COUNT_HYDROGEN_CELL = int(getenv_or_exit("HYDROGEN_CELL_SUM_COUNT_HYDROGEN_CELL", 0))

HYDROGEN_CELL_DATA = getenv_or_exit("TOPIC_HYDROGEN_CELL_SUM_HYDROGEN_CELL_DATA", "default")

HYDROGEN_CELL_DATA_LIST = []
for i in range(COUNT_HYDROGEN_CELL):
    HYDROGEN_CELL_DATA_LIST.append(HYDROGEN_CELL_DATA+str(i))

SUM_HYDROGEN = 0
COUNT = 0
HYDROGEN_LIST = []
COUNT_TICKS_MAX = 24*4
COUNT_TICKS = 0
for i in range(COUNT_TICKS_MAX):
    HYDROGEN_LIST.append(0)

def calc_mean():
    global SUM_HYDROGEN, MEAN_HYDROGEN, HYDROGEN_LIST
    summe = 0
    count = 0
    for i in range(COUNT_TICKS_MAX):
        if HYDROGEN_LIST[i] > 0:
                summe += HYDROGEN_LIST[i]
                count += 1
        if count > 0:
            MEAN_HYDROGEN = round(summe / count, 2)
        else:
            MEAN_HYDROGEN = 0


def on_message_power(client, userdata, msg):
    global HYDROGEN_CELL_SUM_DATA
    global COUNT, COUNT_TICKS_MAX, COUNT_TICKS
    global SUM_HYDROGEN, MEAN_HYDROGEN, HYDROGEN_LIST
    global COUNT_HYDROGEN_CELL

    payload = json.loads(msg.payload) 
    hydrogen = payload["hydrogen"]
    timestamp = payload["timestamp"]
    if COUNT % COUNT_HYDROGEN_CELL == 0:
        SUM_HYDROGEN = hydrogen
    else:
        SUM_HYDROGEN += hydrogen
        HYDROGEN_LIST[COUNT_TICKS] = SUM_HYDROGEN
        calc_mean()
        COUNT_TICKS = (COUNT_TICKS + 1) % COUNT_TICKS_MAX
        if COUNT == COUNT_HYDROGEN_CELL-1:
            # Extract the timestamp from the tick message and decode it from UTF-8
            data = {"hydrogen": SUM_HYDROGEN, "mean_hydrogen": MEAN_HYDROGEN, "timestamp": timestamp}
            # Publish the data to the chaos sensor topic in JSON format
            client.publish(HYDROGEN_CELL_SUM_DATA, json.dumps(data))
    COUNT = (COUNT + 1) % COUNT_HYDROGEN_CELL
    

def main():
    """
    Main function to initialize the MQTT client, set up subscriptions, 
    and start the message loop.
    """
    
    # Initialize the MQTT client and connect to the broker
    mqtt = MQTTWrapper('mqttbroker', 1883, name='hydrogen_cell_sum')
    
    for topic in HYDROGEN_CELL_DATA_LIST:
        # Subscribe to the tick topic
        mqtt.subscribe(topic)
        # Subscribe with a callback function to handle incoming tick messages
        mqtt.subscribe_with_callback(topic, on_message_power)
    
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

