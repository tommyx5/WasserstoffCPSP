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
DISTILLATION_SYSTEM_SUM_DATA = getenv_or_exit("TOPIC_DISTILLATION_SYSTEM_SUM_DISTILLATION_SYSTEM_SUM_DATA", "default")

# MQTT topic for receiving tick messages
COUNT_DISTILLATION_SYSTEM = int(getenv_or_exit("DISTILLATION_SYSTEM_SUM_COUNT_DISTILLATION_SYSTEM", 0))

DISTILLATION_SYSTEM_DATA = getenv_or_exit("TOPIC_DISTILLATION_SYSTEM_SUM_DISTILLATION_SYSTEM_DATA", "default")

DISTILLATION_SYSTEM_DATA_LIST = []
for i in range(COUNT_DISTILLATION_SYSTEM):
    DISTILLATION_SYSTEM_DATA_LIST.append(DISTILLATION_SYSTEM_DATA+str(i))

SUM_DWATER = 0
COUNT = 0
MEAN_DWATER = 0
DWATER_LIST = []
COUNT_TICKS_MAX = 24*4
COUNT_TICKS = 0
for i in range(COUNT_TICKS_MAX):
    DWATER_LIST.append(0)

def calc_mean():
    global SUM_DWATER, MEAN_DWATER, DWATER_LIST
    summe = 0
    count = 0
    for i in range(COUNT_TICKS_MAX):
        if DWATER_LIST[i] > 0:
                summe += DWATER_LIST[i]
                count += 1
        if count > 0:
            MEAN_DWATER = round(summe / count, 2)
        else:
            MEAN_DWATER = 0


def on_message_power(client, userdata, msg):
    global DISTILLATION_SYSTEM_SUM_DATA
    global COUNT, COUNT_TICKS_MAX, COUNT_TICKS
    global SUM_DWATER, MEAN_DWATER, DWATER_LIST
    global COUNT_DISTILLATION_SYSTEM

    payload = json.loads(msg.payload) 
    dwater = payload["dwater"]
    timestamp = payload["timestamp"]
    if COUNT % COUNT_DISTILLATION_SYSTEM == 0:
        SUM_DWATER = dwater
    else:
        SUM_DWATER += dwater
        DWATER_LIST[COUNT_TICKS] = SUM_DWATER
        calc_mean()
        COUNT_TICKS = (COUNT_TICKS + 1) % COUNT_TICKS_MAX
        if COUNT == COUNT_DISTILLATION_SYSTEM-1:
            # Extract the timestamp from the tick message and decode it from UTF-8
            data = {"dwater": SUM_DWATER, "mean_dwater": MEAN_DWATER, "timestamp": timestamp}
            # Publish the data to the chaos sensor topic in JSON format
            client.publish(DISTILLATION_SYSTEM_SUM_DATA, json.dumps(data))
    COUNT = (COUNT + 1) % COUNT_DISTILLATION_SYSTEM
    

def main():
    """
    Main function to initialize the MQTT client, set up subscriptions, 
    and start the message loop.
    """
    
    # Initialize the MQTT client and connect to the broker
    mqtt = MQTTWrapper('mqttbroker', 1883, name='distillation_system_sum')
    
    for topic in DISTILLATION_SYSTEM_DATA_LIST:
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

