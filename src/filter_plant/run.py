import sys
import json
import logging
from mqtt.mqtt_wrapper import MQTTWrapper
import os
import threading

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

TOPIC_FOR_POWER = getenv_or_exit("TOPIC_POWER_SUM_POWER_SUM_DATA", "default")
TOPIC_FOR_DEP = getenv_or_exit('TOPIC_WATER_PIPE_SUPPLY', "default")

AVAILABLE = 0 
TIMESTAMP = 0

class StateManager:
    STATES = ['WAITING_FOR_POWER', 'WAITING_FOR_DEPENDENCY', 'WAITING_FOR_TICK', 'READY_TO_PROCESS', 'PROCESSING', 'DONE']

    def __init__(self, dependencies=None):
        self.state = 'WAITING_FOR_POWER'
        self.lock = threading.Lock()
        self.power_received = False
        self.dependency_received = False
        self.tick_received = False
        self.dependencies_met = False

    def receive_power(self):
        with self.lock:
            self.power_received = True
            self._update_state()

    def receive_dependency(self):
        with self.lock:
            self.dependency_received = True
            self._update_state()

    def receive_tick(self):
        with self.lock:
            self.tick_received = True
            self._update_state()

    def _update_state(self):
        # Update the container state based on the current conditions
        if self.power_received and self.dependency_received:
            self.state = 'READY_TO_PROCESS'
        elif self.power_received:
            self.state = 'WAITING_FOR_DEPENDENCY'
        else:
            self.state = 'WAITING_FOR_POWER'

    def is_ready_to_process(self):
        return self.state == 'READY_TO_PROCESS'

    def start_processing(self):
        with self.lock:
            if self.state == 'READY_TO_PROCESS':
                self.state = 'PROCESSING'
                return True
            return False

    def complete_processing(self):
        with self.lock:
            if self.state == 'PROCESSING':
                self.state = 'DONE'
                self._reset_state_for_next_tick()

    def _reset_state_for_next_tick(self):
        # Reset state for the next tick
        self.state = 'WAITING_FOR_POWER'
        self.power_received = False
        self.dependency_received = False
        self.tick_received = False

state_manager = StateManager()

def process(client):
    global AVAILABLE, TOPIC_FILTERED_WATER_SUPPLY, TIMESTAMP
    filtered_water_supply = filter_water(AVAILABLE)
    AVAILABLE = 0
                    
    data = { 
        "filteredwatersupply": filtered_water_supply, 
        "timestamp": TIMESTAMP
    }
    # Publish the data to the topic in JSON format
    client.publish(TOPIC_FILTERED_WATER_SUPPLY, json.dumps(data))


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
    global AVAILABLE, state_manager, TIMESTAMP

    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    water_supply = payload["watersupply"]
    
    TIMESTAMP = timestamp
    AVAILABLE = water_supply
    state_manager.receive_dependency()  # Mark water as received in state manager

def on_message_power_received(client, userdata, msg):
    """
    Callback function that processes messages from the tick generator topic.
    It publishes topic with request for water and power
    
    Parameters:
    client (MQTT client): The MQTT client instance
    msg (MQTTMessage): The message containing the tick timestamp
    """
    global POWER_DEMAND
    global state_manager, TIMESTAMP, TOPIC_FILTERED_WATER_SUPPLY

    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    #power_supply = payload["powersupply"]
    power_supply = payload["power"]
    
    TIMESTAMP = timestamp
    
    if power_supply < POWER_DEMAND:
        # publish zero topic
        data = { 
        "filteredwatersupply": 0, 
        "timestamp": timestamp
        }
        client.publish(TOPIC_FILTERED_WATER_SUPPLY, json.dumps(data))
    else:
        state_manager.receive_power()
    

def main():
    """
    Main function to initialize the MQTT client, set up subscriptions, 
    and start the message loop.
    """
    
    # Initialize the MQTT client and connect to the broker
    mqtt = MQTTWrapper('mqttbroker', 1883, name='filter_plant_' + ID)
    

    mqtt.subscribe(TOPIC_FOR_DEP)
    mqtt.subscribe(TOPIC_FOR_POWER)
    mqtt.subscribe_with_callback(TOPIC_FOR_DEP, on_message_water_received)
    mqtt.subscribe_with_callback(TOPIC_FOR_POWER, on_message_power_received)
    
    try:
        while True:
            if state_manager.is_ready_to_process():
                if state_manager.start_processing():
                    # Perform processing here
                    #print("Processing water with sufficient energy and dependencies.")
                    # 
                    process(mqtt)
                    
                    state_manager.complete_processing()
            
            mqtt.loop(0.1) # loop every 100ms
    except (KeyboardInterrupt, SystemExit):
        mqtt.stop()
        sys.exit("KeyboardInterrupt -- shutdown gracefully.")

if __name__ == '__main__':
    # Entry point for the script
    main()
