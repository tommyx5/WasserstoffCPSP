import sys
import json
import logging
from mqtt.mqtt_wrapper import MQTTWrapper
import math



def on_message_water_received(client, userdata, msg):

    """
    Callback function that processes messages from the tick generator topic.
    It generates a random sensor value and publishes it along with the tick's timestamp.
    
    Parameters:
    client (MQTT client): The MQTT client instance
    userdata: User-defined data (not used here)
    msg (MQTTMessage): The message containing the tick timestamp
    """
    global WIND_POWER_DATA
    global AREA
    global RATED_POWER
    global ID_S
    
    payload = json.loads(msg.payload) 
    timestamp = payload["timestamp"]
    density = payload["density"]
    temperature = payload["temperature"]
    windspeed = payload["windspeed"]

    # Important: Always send your data with the timestamp from the Tick message.
    # Node Red is designed for real-time or historical messages, so discrepancies 
    # in timestamps can cause errors in the display.
    power = round(calc_power(AREA, density, windspeed),2)
    if power >= RATED_POWER*1.02:
        power = 0
    data = {"id": ID_S, "power": power, "timestamp": timestamp}
    # Publish the data to the chaos sensor topic in JSON format
    client.publish(WIND_POWER_DATA, json.dumps(data))

def main():
    """
    Main function to initialize the MQTT client, set up subscriptions, 
    and start the message loop.
    """
    
    # Initialize the MQTT client and connect to the broker
    mqtt = MQTTWrapper('mqttbroker', 1883, name='filter_plant')
    
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
