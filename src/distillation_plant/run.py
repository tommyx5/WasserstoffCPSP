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

ID = getenv_or_exit("ID", "default")
WATER_DEMAND = float(getenv_or_exit("DISTIL_PLANT_" + ID + "_FILTERED_WATER_DEMAND", 0.0)) # in m^3
POWER_DEMAND = float(getenv_or_exit("DISTIL_PLANT_" + ID + "_POWER_DEMAND", 0.0)) # in kW
WATER_SUPPLY = float(getenv_or_exit("DISTIL_PLANT_" + ID + "_DISTILLED_WATER_MAX_SUPPLY", 0.0)) # in m^3

TICK = getenv_or_exit("TOPIC_TICK_GEN_TICK", "default")
TOPIC_WATER_REQUEST = getenv_or_exit("TOPIC_FILTER_SUM_FILTERED_WATER_REQUEST", "default") # topic to request water
TOPIC_WATER_RECIEVE = getenv_or_exit("TOPIC_DISTIL_PLANT_FILTERED_WATER_RECIEVE", "default") + ID # must be followed by filter plant id
TOPIC_POWER_REQUEST = getenv_or_exit("TOPIC_POWER_SUM_POWER_REQUEST", "default") # topic to request power
TOPIC_POWER_RECIEVE = getenv_or_exit("TOPIC_DISTIL_PLANT_POWER_RECIEVE", "default") + ID # must be followed by filter plant id
TOPIC_DISTILLED_WATER_SUPPLY = getenv_or_exit("TOPIC_DISTIL_PLANT_DISTILLED_WATER_SUPPLY", "default") + ID # must be followed by filter plant id

POWER_AVAILABLE = False

def not_enough_power():
    global POWER_AVAILABLE
    POWER_AVAILABLE = False

def enough_power():
    global POWER_AVAILABLE
    POWER_AVAILABLE = True

def distill_water(water_supplied):
    global WATER_DEMAND, WATER_SUPPLY, POWER_AVAILABLE

    distilled_water = 0

    if not POWER_AVAILABLE:
        print("Power Outage! Not enough power to filter the water")
        #return 0

    if water_supplied < WATER_DEMAND:
        distilled_water = water_supplied
    else:
        distilled_water = WATER_SUPPLY
    return distilled_water

def on_message_water_received(client, userdata, msg):
    """
    Callback function that processes messages from the water received topic.
    It processes how much water is received from water pipe and generates the coresponding volume of filtered volume.
    After that publishes it along with the timestamp.
    """
    global TOPIC_DISTILLED_WATER_SUPPLY

    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    water_supply = payload["filteredwatersupply"]

    distilled_water_supply = distill_water(water_supply)

    data = { 
        "distilledwatersupply": distilled_water_supply, 
        "timestamp": timestamp
    }

    # Publish the data to the topic in JSON format
    client.publish(TOPIC_DISTILLED_WATER_SUPPLY, json.dumps(data))

def on_message_tick(client, userdata, msg):
    """
    Callback function that processes messages from the tick generator topic.
    It publishes topic with request for water and power
    
    Parameters:
    client (MQTT client): The MQTT client instance
    msg (MQTTMessage): The message containing the tick timestamp
    """
    global WATER_DEMAND, TOPIC_WATER_RECIEVE, TOPIC_WATER_REQUEST
    global POWER_DEMAND, TOPIC_POWER_RECIEVE, TOPIC_POWER_REQUEST
    
    #extracting the timestamp 
    timestamp = msg.payload.decode("utf-8")

    #creating the new data
    data_water = {
        "topic": TOPIC_WATER_RECIEVE, # topic for water pipe to publish the reply on
        "filteredwaterdemand": WATER_DEMAND, 
        "timestamp": timestamp
    }
    data_power = {
        "topic": TOPIC_POWER_RECIEVE, # topic for power sum to publish the reply on
        "powerdemand": POWER_DEMAND, 
        "timestamp": timestamp
    }
    
    client.publish(TOPIC_WATER_REQUEST, json.dumps(data_water))
    client.publish(TOPIC_POWER_REQUEST, json.dumps(data_power))

def on_message_power_received(client, userdata, msg):
    """
    Callback function that processes messages from the tick generator topic.
    It publishes topic with request for water and power
    
    Parameters:
    client (MQTT client): The MQTT client instance
    msg (MQTTMessage): The message containing the tick timestamp
    """
    global POWER_DEMAND

    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    power_supply = payload["powersupply"]

    if(power_supply < POWER_DEMAND):
        not_enough_power()
    else:
        enough_power()

def main():
    """
    Main function to initialize the MQTT client, set up subscriptions, 
    and start the message loop.
    """
    
    # Initialize the MQTT client and connect to the broker
    mqtt = MQTTWrapper('mqttbroker', 1883, name='distil_plant_' + ID)
    
    mqtt.subscribe(TICK)
    mqtt.subscribe(TOPIC_WATER_RECIEVE)
    mqtt.subscribe(TOPIC_POWER_RECIEVE)
    mqtt.subscribe_with_callback(TICK, on_message_tick)
    mqtt.subscribe_with_callback(TOPIC_WATER_RECIEVE, on_message_water_received)
    mqtt.subscribe_with_callback(TOPIC_POWER_RECIEVE, on_message_power_received)
    
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
