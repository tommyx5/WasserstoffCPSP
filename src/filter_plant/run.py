import sys
import json
import logging
from mqtt.mqtt_wrapper import MQTTWrapper
from statemanager import StateManager  # Import the state manager
import os

def getenv_or_exit(env_name, default="default"):
    value = os.getenv(env_name, default)
    if value == default:
        raise SystemExit(f"Environment variable {env_name} not set")
    return value

ID = getenv_or_exit("ID", "default")
WATER_DEMAND = float(getenv_or_exit("FILTER_PLANT_" + ID + "_WATER_DEMAND", 0.0)) # in m^3
POWER_DEMAND = float(getenv_or_exit("FILTER_PLANT_" + ID + "_POWER_DEMAND", 0.0)) # in kW
WATER_SUPPLY = float(getenv_or_exit("FILTER_PLANT_" + ID + "_FILTERED_WATER_MAX_SUPPLY", 0.0)) # in m^3

TICK = getenv_or_exit("TOPIC_TICK_GEN_TICK", "default")
TOPIC_WATER_REQUEST = getenv_or_exit("TOPIC_WATER_PIPE_WATER_REQUEST", "default") # topic to request water
TOPIC_WATER_RECIEVE = getenv_or_exit("TOPIC_FILTER_PLANT_WATER_RECIEVE", "default") + ID # must be followed by filter plant id
TOPIC_POWER_REQUEST = getenv_or_exit("TOPIC_POWER_SUM_POWER_REQUEST", "default") # topic to request power
TOPIC_POWER_RECIEVE = getenv_or_exit("TOPIC_FILTER_PLANT_POWER_RECIEVE", "default") + ID # must be followed by filter plant id
TOPIC_FILTERED_WATER_SUPPLY = getenv_or_exit("TOPIC_FILTER_PLANT_FILTERED_WATER_SUPPLY", "default") + ID # must be followed by filter plant id

# State Manager for handling dependency management
state_manager = StateManager()
AVAILABLE = 0 
TIMESTAMP = 0

def filter_water(water_supplied):
    global WATER_DEMAND, WATER_SUPPLY

    filtered_water = 0

    if water_supplied < WATER_DEMAND:
        filtered_water = water_supplied
    else:
        filtered_water = WATER_SUPPLY
    return filtered_water

def on_message_water_received(client, userdata, msg):
    """
    Callback function that processes messages from the water received topic.
    It processes how much water is received from water pipe and generates the coresponding volume of filtered volume.
    After that publishes it along with the timestamp.
    """
    global TOPIC_FILTERED_WATER_SUPPLY
    global AVAILABLE, state_manager

    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    water_supply = payload["watersupply"]
    
    AVAILABLE = water_supply
    state_manager.receive_water()  # Mark water as received in state manager

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
    global state_manager, TIMESTAMP, AVAILABLE
    
    #extracting the timestamp 
    timestamp = msg.payload.decode("utf-8")

    #creating the new data
    data_water = {
        "topic": TOPIC_WATER_RECIEVE, # topic for water pipe to publish the reply on
        "waterdemand": WATER_DEMAND, 
        "timestamp": timestamp
    }
    data_power = {
        "topic": TOPIC_POWER_RECIEVE, # topic for power sum to publish the reply on
        "powerdemand": POWER_DEMAND, 
        "timestamp": timestamp
    }

    state_manager._reset_state_for_next_tick()
    AVAILABLE = 0
    TIMESTAMP = timestamp
    state_manager.receive_tick()  # Mark tick as received in state manager
    
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
    global state_manager

    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    power_supply = payload["powersupply"]

    if power_supply >= POWER_DEMAND:
        state_manager.receive_energy()  # Mark power as received in state manager
    else:
        print("Insufficient power supply.")


def main():
    """
    Main function to initialize the MQTT client, set up subscriptions, 
    and start the message loop.
    """
    
    # Initialize the MQTT client and connect to the broker
    mqtt = MQTTWrapper('mqttbroker', 1883, name='filter_plant_' + ID)
    
    mqtt.subscribe(TICK)
    mqtt.subscribe(TOPIC_WATER_RECIEVE)
    mqtt.subscribe(TOPIC_POWER_RECIEVE)
    mqtt.subscribe_with_callback(TICK, on_message_tick)
    mqtt.subscribe_with_callback(TOPIC_WATER_RECIEVE, on_message_water_received)
    mqtt.subscribe_with_callback(TOPIC_POWER_RECIEVE, on_message_power_received)
    
    try:
        while True:
            if state_manager.is_ready_to_process():
                if state_manager.start_processing():
                    # Perform processing here
                    #print("Processing water with sufficient energy and dependencies.")
                    # filter_water()
                    filtered_water_supply = filter_water(AVAILABLE)
                    
                    data = { 
                        "filteredwatersupply": filtered_water_supply, 
                        "timestamp": TIMESTAMP
                    }
                    # Publish the data to the topic in JSON format
                    mqtt.publish(TOPIC_FILTERED_WATER_SUPPLY, json.dumps(data))
                    
                    state_manager.complete_processing()
            
            mqtt.loop(0.1) # loop every 100ms
    except (KeyboardInterrupt, SystemExit):
        mqtt.stop()
        sys.exit("KeyboardInterrupt -- shutdown gracefully.")

if __name__ == '__main__':
    # Entry point for the script
    main()
