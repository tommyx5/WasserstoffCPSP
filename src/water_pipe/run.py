import sys
import json
import logging
from mqtt.mqtt_wrapper import MQTTWrapper
import math
import os

# topic for receiving tick messages
TICK = os.getenv('TOPIC_TICK', 'default')
print("Tick ", TICK)
# topic for publishing water volume
TOPIC_WATER = os.getenv('TOPIC_WATER_PIPE_VOLUME', "default")
print("water ", TOPIC_WATER)
# Water volume (in m^3) supplied by the pipe
WATER_VOLUME = float(os.getenv('WATER_PIPE_VOLUME', 0.0))
print("volume ", WATER_VOLUME)

def on_message_tick(client, userdata, msg):
    """
    Callback function that processes messages from the tick generator topic.
    It publishes the volume of water that can be supplied by the pipe
    
    Parameters:
    client (MQTT client): The MQTT client instance
    userdata: User-defined data (not used here)
    msg (MQTTMessage): The message containing the tick timestamp
    """
    global WATER_VOLUME
    global TOPIC_WATER
    
    payload = json.loads(msg.payload) 
    timestamp = payload["timestamp"]
    data = {"water_volume": WATER_VOLUME, "timestamp": timestamp}
    client.publish(TOPIC_WATER, json.dumps(data))

def main():
    """
    Main function to initialize the MQTT client, set up subscriptions, 
    and start the message loop.
    """
    
    # Initialize the MQTT client and connect to the broker
    mqtt = MQTTWrapper('mqttbroker', 1883, name='water_pipe')
    
    # Subscribe to the tick topic
    mqtt.subscribe(TICK)
    # Subscribe with a callback function to handle incoming tick messages
    mqtt.subscribe_with_callback(TICK, on_message_tick)
    
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
