import sys
import json
import logging
from mqtt.mqtt_wrapper import MQTTWrapper
from datetime import datetime
from meteostat import Point, Daily, Hourly
import os

RS =  287.1 #J/(kg·K)
HEKTO = 100
CELSIUS_IN_KELVIN = 273.15

def getenv_or_exit(env_name, default="default"):
    value = os.getenv(env_name, default)
    if value == default:
        raise SystemExit(f"Environment variable {env_name} not set")
    return value

LATITUDE = float(getenv_or_exit("CLIMATE_GEN_COORDINATES_LATITUDE", -1.0)) 
LONGITUDE = float(getenv_or_exit("CLIMATE_GEN_COORDINATES_LONGITUDE", -1.0))
ALTITUDE = int(getenv_or_exit("CLIMATE_GEN_COORDINATES_ALTITUDE", -1))
# Create Point for Hamburg Koordinaten: 53° 33′ N, 10° 0′ O 6m
POINT = Point(LATITUDE, LONGITUDE, ALTITUDE)

START_YEAR = int(getenv_or_exit('TICK_GEN_START_YEAR', 0))
START_MONTH = int(getenv_or_exit('TICK_GEN_START_MONTH', 0))
START_DAY = int(getenv_or_exit('TICK_GEN_START_DAY', 0))
start = datetime(START_YEAR, START_MONTH, START_DAY)
end = datetime(2022, 12, 31, 23, 59)

# Get daily data for 2018 - 2022
data = Hourly(POINT, start, end)
data = data.fetch()

p = data['pres']
t = data['temp']
s = data['wspd']

p1 = []
for i in range(len(p)):
    p1.append(round((p[i]*HEKTO)/(RS*(t[i]+CELSIUS_IN_KELVIN)), 2))

DATA = [p1,t,s]

LENGTH = len(DATA[0])
POS = 0
COUNT = 0
DIVIDE = 4

NAME = getenv_or_exit("CLIMATE_GEN_NAME", "default")
# MQTT topic for publishing sensor data
CLIMATE_DATA = getenv_or_exit("TOPIC_CLIMATE_GEN_CLIMATE_DATA", "default")
# MQTT topic for receiving tick messages
TICK_TOPIC = getenv_or_exit("TOPIC_TICK_GEN_TICK", "default")

def on_message_tick(client, userdata, msg):
    """
    Callback function that processes messages from the tick generator topic.
    It generates a random sensor value and publishes it along with the tick's timestamp.
    
    Parameters:
    client (MQTT client): The MQTT client instance
    userdata: User-defined data (not used here)
    msg (MQTTMessage): The message containing the tick timestamp
    """
    global DATA, POS, LENGTH, DIVIDE, COUNT
    
    # Extract the timestamp from the tick message and decode it from UTF-8
    ts_iso = msg.payload.decode("utf-8")

    # Important: Always send your data with the timestamp from the Tick message.
    # Node Red is designed for real-time or historical messages, so discrepancies 
    # in timestamps can cause errors in the display.
    alpha = (COUNT%DIVIDE)/DIVIDE
    density = round((DATA[0][POS] * (1 - alpha) + DATA[0][(POS + 1) % LENGTH] * alpha),2)
    temperature = round((DATA[1][POS] * (1 - alpha) + DATA[1][(POS + 1) % LENGTH] * alpha),2)
    windspeed = round((DATA[2][POS] * (1 - alpha) + DATA[2][(POS + 1) % LENGTH] * alpha),2)

    data = {"density": density, "temperature": temperature, "windspeed": windspeed, "timestamp": ts_iso}
    # Publish the data to the chaos sensor topic in JSON format
    client.publish(CLIMATE_DATA, json.dumps(data))
    COUNT += 1
    if (COUNT%DIVIDE) == 0:
        POS = (POS + 1) % LENGTH
        COUNT = 0

def main():
    """
    Main function to initialize the MQTT client, set up subscriptions, 
    and start the message loop.
    """
    
    # Initialize the MQTT client and connect to the broker
    mqtt = MQTTWrapper('mqttbroker', 1883, name='climate_gen_'+NAME)
    
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

