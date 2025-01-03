import sys
import json
import logging
from mqtt.mqtt_wrapper import MQTTWrapper
import math
import os
from random import seed, randint

def getenv_or_exit(env_name, default="default"):
    value = os.getenv(env_name, default)
    if value == default:
        raise SystemExit(f"Environment variable {env_name} not set")
    return value

ID = getenv_or_exit("ID", "default")

UPPER_CUT_OUT_WIND_SPEED = float(getenv_or_exit("POWER_PLANT_" + ID + "_UPPER_CUT_OUT_WIND_SPEED", "0.0")) 
LOWER_CUT_OUT_WIND_SPEED = float(getenv_or_exit("POWER_PLANT_" + ID + "_LOWER_CUT_OUT_WIND_SPEED", "0.0"))

KMH_IN_MS = 1000/3600
WATT_IN_KILOWATT = 1000
PERCENT = 100
POW2 = 2
POW3 = 3
SEED = 42

CP = [0.0, 0.12,0.29,0.4,0.43,0.46,0.48,0.49,0.5,0.49,0.44,0.39,0.35,0.3,0.26,0.22,0.19,0.16,0.14,0.12,0.1,0.09,0.08,0.07,0.06]

def calc_area(diameter):
    return math.pi*math.pow(diameter/2,POW2)

def calc_power(area, density, windspeed):
    global CP
    cp = 0
    if windspeed < 26:
        cp = CP[int(windspeed)%len(CP)]
    else:
        cp = 0
    cp = 0.5
    return (0.5*area*density*math.pow(windspeed*KMH_IN_MS,POW3)*cp)/WATT_IN_KILOWATT

MODEL = getenv_or_exit("POWER_PLANT_" + ID + "_MODEL", "default")
ROTOR_DIAMETER = float(getenv_or_exit("POWER_PLANT_" + ID + "_ROTOR_DIAMETER", 0.0)) #meter
AREA = calc_area(ROTOR_DIAMETER)
RATED_POWER = float(getenv_or_exit("POWER_PLANT_" + ID + "_RATED_POWER", 0.0)) #kW
NAME = getenv_or_exit("POWER_PLANT_" + ID + "_NAME", "default")

# MQTT topic for publishing sensor data
TOPIC_WIND_POWER_DATA = getenv_or_exit("TOPIC_POWER_PLANT_POWER_DATA", "default") + ID # must be followed by the power plant id

# MQTT topic for receiving tick messages
CLIMATE_DATA = getenv_or_exit("TOPIC_CLIMATE_GEN_CLIMATE_DATA", "default")

def on_message_weather(client, userdata, msg):
    """
    Callback function that processes messages from the tick generator topic.
    It generates a random sensor value and publishes it along with the tick's timestamp.
    
    Parameters:
    client (MQTT client): The MQTT client instance
    userdata: User-defined data (not used here)
    msg (MQTTMessage): The message containing the tick timestamp
    """
    global TOPIC_WIND_POWER_DATA
    global AREA
    global RATED_POWER
    global ID
    
    payload = json.loads(msg.payload) 
    timestamp = payload["timestamp"]
    density = payload["density"]
    temperature = payload["temperature"]
    windspeed = payload["windspeed"]

    # Important: Always send your data with the timestamp from the Tick message.
    # Node Red is designed for real-time or historical messages, so discrepancies 
    # in timestamps can cause errors in the display.
    power = round(calc_power(AREA, density, windspeed),2)+randint(0, 100)
    if power > RATED_POWER:
        print(f"Actual power output {power} exceeds rated power output {RATED_POWER}")
        power = RATED_POWER-randint(0, 100)
    data = {"id": ID, "power": power, "timestamp": timestamp}
    # Publish the data to the chaos sensor topic in JSON format
    client.publish(TOPIC_WIND_POWER_DATA, json.dumps(data))

def main():
    """
    Main function to initialize the MQTT client, set up subscriptions, 
    and start the message loop.
    """
    
    # Initialize the MQTT client and connect to the broker
    mqtt = MQTTWrapper('mqttbroker', 1883, name='wind_power_plant_' + ID)
    
    # Subscribe to the tick topic
    mqtt.subscribe(CLIMATE_DATA)
    # Subscribe with a callback function to handle incoming tick messages
    mqtt.subscribe_with_callback(CLIMATE_DATA, on_message_weather)
    
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
