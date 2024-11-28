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

COUNT_FILTER_SYSTEM = int(getenv_or_exit("FILTER_SUM_COUNT_FILTER", 0))

TICK = getenv_or_exit('TOPIC_TICK_GEN_TICK', 'default')
FILTER_SYSTEM_SUM_DATA = getenv_or_exit("TOPIC_FILTER_SUM_FILTER_SUM_DATA", "default")
FILTER_SYSTEM_DATA = getenv_or_exit("TOPIC_FILTER_PLANT_FILTERED_WATER_SUPPLY", "default")
TOPIC_REQUEST = getenv_or_exit("TOPIC_FILTER_SUM_FILTERED_WATER_REQUEST", "default")

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

AVAILABLE = 0

def on_message_tick(client, userdata, msg):
    # reset each tick available power to 0
    global AVAILABLE
    AVAILABLE =  0

def calculate_supply(demand):
    global AVAILABLE

    supplied = 0
    if(demand < AVAILABLE):
        supplied = demand
        AVAILABLE = AVAILABLE - demand
    else:
        supplied = AVAILABLE
        AVAILABLE = 0
    return supplied

def on_message_request(client, userdata, msg):
    """
    Callback function that processes messages from the request topic.
    It publishes the FILTERED WATER that can be supplied to the received topic
    
    Parameters:
    client (MQTT client): The MQTT client instance
    msg (MQTTMessage): The message containing the tick timestamp
    """
    
    #extracting the timestamp and other data
    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    topic = payload["topic"] # topic to publish the supplied power to
    demand = payload["filteredwaterdemand"]

    suplied = calculate_supply(demand)
    
    data = {
        "filteredwatersupply": suplied, 
        "timestamp": timestamp
    }

    client.publish(topic, json.dumps(data))

def calc_mean():
    global SUM_FWATER, MEAN_FWATER, FWATER_LIST
    summe = 0
    count = 0
    for i in range(COUNT_TICKS_MAX):
        if FWATER_LIST[i] > 0:
                summe += FWATER_LIST[i]
                count += 1
        if count > 0:
            MEAN_FWATER = round(summe / count, 2)
        else:
            MEAN_FWATER = 0

def on_message_power(client, userdata, msg):
    global FILTER_SYSTEM_SUM_DATA
    global COUNT, COUNT_TICKS_MAX, COUNT_TICKS
    global SUM_FWATER, MEAN_FWATER, FWATER_LIST
    global COUNT_FILTER_SYSTEM
    global AVAILABLE

    payload = json.loads(msg.payload) 
    fwater = payload["filteredwatersupply"]
    timestamp = payload["timestamp"]

    AVAILABLE = AVAILABLE + fwater

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
    
    mqtt.subscribe(TICK)
    mqtt.subscribe_with_callback(TICK, on_message_tick)
    mqtt.subscribe(TOPIC_REQUEST)
    mqtt.subscribe_with_callback(TOPIC_REQUEST, on_message_request)

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

