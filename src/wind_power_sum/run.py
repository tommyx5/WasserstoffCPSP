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

COUNT_POWER_GEN = int(getenv_or_exit("POWER_SUM_COUNT_POWER_GEN", 0))

TICK = getenv_or_exit('TOPIC_TICK_GEN_TICK', 'default')
WIND_POWER_SUM_DATA = getenv_or_exit("TOPIC_POWER_SUM_POWER_SUM_DATA", "default")
WIND_POWER_DATA = getenv_or_exit("TOPIC_POWER_PLANT_POWER_DATA", "default")
TOPIC_REQUEST = getenv_or_exit("TOPIC_POWER_SUM_POWER_REQUEST", "default")

WIND_POWER_DATA_LIST = []
for i in range(COUNT_POWER_GEN):
    WIND_POWER_DATA_LIST.append(WIND_POWER_DATA+str(i))

SUM_POWER = 0
COUNT = 0
MEAN_POWER = 0
POWER_LIST = []
COUNT_TICKS_MAX = 24*4
COUNT_TICKS = 0
for i in range(COUNT_TICKS_MAX):
    POWER_LIST.append(0)

available_power = 0    

def calc_mean():
    global SUM_POWER, MEAN_POWER, POWER_LIST
    summe = 0
    count = 0
    for i in range(COUNT_TICKS_MAX):
        if POWER_LIST[i] > 0:
            summe += POWER_LIST[i]
            count += 1
    if count > 0:
        MEAN_POWER = round(summe / count, 2)
    else:
        MEAN_POWER = 0

def on_message_tick(client, userdata, msg):
    # reset each tick available power to 0
    global available_power
    available_power =  1000

def calculate_supply(demand):
    global available_power

    power_supplied = 0
    if(demand < available_power):
        power_supplied = demand
        available_power = available_power - demand
    else:
        power_supplied = available_power
        available_power = 0
    return power_supplied

def on_message_power(client, userdata, msg):
    global WIND_POWER_SUM_DATA
    global COUNT, COUNT_TICKS_MAX, COUNT_TICKS
    global SUM_POWER, MEAN_POWER, POWER_LIST, available_power
    global COUNT_POWER_GEN

    payload = json.loads(msg.payload) 
    power = payload["power"]
    timestamp = payload["timestamp"]

    available_power = available_power + power # update available power
    
    if COUNT % COUNT_POWER_GEN == 0:
        SUM_POWER = power
    else:
        SUM_POWER += power
        POWER_LIST[COUNT_TICKS] = SUM_POWER
        calc_mean()
        COUNT_TICKS = (COUNT_TICKS + 1) % COUNT_TICKS_MAX
        if COUNT == COUNT_POWER_GEN-1:
            # Extract the timestamp from the tick message and decode it from UTF-8
            data = {"power": SUM_POWER, "mean_power": MEAN_POWER, "timestamp": timestamp}
            # Publish the data to the chaos sensor topic in JSON format
            client.publish(WIND_POWER_SUM_DATA, json.dumps(data))
    COUNT = (COUNT + 1) % COUNT_POWER_GEN
    
def on_message_request(client, userdata, msg):
    """
    Callback function that processes messages from the request topic.
    It publishes the power that can be supplied to the received topic
    
    Parameters:
    client (MQTT client): The MQTT client instance
    msg (MQTTMessage): The message containing the tick timestamp
    """
    
    #extracting the timestamp and other data
    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    topic = payload["topic"] # topic to publish the supplied power to
    demand = payload["powerdemand"]

    power_suplied = calculate_supply(demand)
    
    data = {
        "powersupply": power_suplied, 
        "timestamp": timestamp
    }

    client.publish(topic, json.dumps(data))

def main():
    """
    Main function to initialize the MQTT client, set up subscriptions, 
    and start the message loop.
    """
    
    # Initialize the MQTT client and connect to the broker
    mqtt = MQTTWrapper('mqttbroker', 1883, name='wind_power_sum')
    
    mqtt.subscribe(TICK)
    mqtt.subscribe_with_callback(TICK, on_message_tick)
    mqtt.subscribe(TOPIC_REQUEST)
    mqtt.subscribe_with_callback(TOPIC_REQUEST, on_message_request)

    for topic in WIND_POWER_DATA_LIST:
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

