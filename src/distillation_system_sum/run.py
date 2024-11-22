import sys
import json
import logging
from random import seed, randint
from mqtt.mqtt_wrapper import MQTTWrapper

# MQTT topic for publishing sensor data
FILTER_SYSTEM_SUM_DATA = "data/fwater/sum"

# MQTT topic for receiving tick messages
COUNT_FILTER_SYSTEM = 10 #?
FILTER_SYSTEM_DATA = "data/fwater/"
FILTER_SYSTEM_DATA_LIST = []
for i in range(COUNT_FILTER_SYSTEM):
    FILTER_SYSTEM_DATA_LIST.append(FILTER_SYSTEM_DATA+str(i))

SUM_FWATER = 0
COUNT = 0
MEAN_FWATER = 0
FWATER_LIST = []
COUNT_TICKS_MAX = 24*4
COUNT_TICKS = 0
for i in range(COUNT_TICKS_MAX):
    FWATER_LIST.append(0)

def calc_mean():
    global SUM_FWATER, MEAN_FWATER, FWATER_LIST
    summe = 0
    for i in range(COUNT_TICKS_MAX):
        summe += FWATER_LIST[i]
    MEAN_FWATER = round(summe / COUNT_TICKS_MAX, 2)


def on_message_power(client, userdata, msg):
    global FILTER_SYSTEM_SUM_DATA
    global COUNT, COUNT_TICKS_MAX, COUNT_TICKS
    global SUM_FWATER, MEAN_FWATER, FWATER_LIST
    global COUNT_FILTER_SYSTEM

    payload = json.loads(msg.payload) 
    fwater = payload["fwater"]
    timestamp = payload["timestamp"]
    if COUNT % COUNT_FILTER_SYSTEM == 0:
        SUM_FWATER = fwater
    else:
        SUM_FWATER += fwater
        FWATER_LIST[COUNT_TICKS] = SUM_FWATER
        calc_mean()
        COUNT_TICKS = (COUNT_TICKS + 1) % COUNT_TICKS_MAX
        if COUNT == COUNT_FILTER_SYSTEM-1:
            # Extract the timestamp from the tick message and decode it from UTF-8
            data = {"fwater": SUM_FWATER, "mean_fwater": MEAN_FWATER, "timestamp": timestamp}
            # Publish the data to the chaos sensor topic in JSON format
            client.publish(FILTER_SYSTEM_SUM_DATA, json.dumps(data))
    COUNT = (COUNT + 1) % COUNT_FILTER_SYSTEM
    

def main():
    """
    Main function to initialize the MQTT client, set up subscriptions, 
    and start the message loop.
    """
    
    # Initialize the MQTT client and connect to the broker
    mqtt = MQTTWrapper('mqttbroker', 1883, name='filter_system_sum')
    
    for topic in FILTER_SYSTEM_DATA_LIST:
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

