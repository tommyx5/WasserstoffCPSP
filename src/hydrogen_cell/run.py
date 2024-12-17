import sys
import json
import logging
from mqtt.mqtt_wrapper import MQTTWrapper
import math
import os
import threading

def getenv_or_exit(env_name, default="default"):
    value = os.getenv(env_name, default)
    if value == default:
        raise SystemExit(f"Environment variable {env_name} not set")
    return value

ID = getenv_or_exit("ID", "default")
NOMINAL_FILTERED_WATER_DEMAND = float(getenv_or_exit("HYDROGEN_CELL_" + ID + "_DISTILLED_WATER_DEMAND", 0.0)) # in m^3
NOMINAL_POWER_DEMAND = float(getenv_or_exit("HYDROGEN_CELL_" + ID + "_POWER_DEMAND", 0.0)) # in kW
NOMINAL_HYDROGEN_SUPPLY = float(getenv_or_exit("HYDROGEN_CELL_" + ID + "_HYDROGEN_MAX_SUPPLY", 0.0)) # in m^3

TICK = getenv_or_exit("TOPIC_TICK_GEN_TICK", "default")
TOPIC_FILTERED_WATER_REQUEST = getenv_or_exit("TOPIC_FILTERED_WATER_PIPE_FILTERED_WATER_REQUEST", "default") # topic to request water
TOPIC_FILTERED_WATER_RECEIVE = getenv_or_exit("TOPIC_FILTER_PLANT_FILTERED_WATER_RECEIVE", "default") + ID # must be followed by filter plant id
TOPIC_POWER_REQUEST = getenv_or_exit("TOPIC_POWER_SUM_POWER_REQUEST", "default") # topic to request power
TOPIC_POWER_RECEIVE = getenv_or_exit("TOPIC_HYDROGEN_POWER_RECEIVE", "default") + ID # must be followed by filter plant id
TOPIC_HYDROGEN_SUPPLY = getenv_or_exit("TOPIC_HYDROGEN_HYDROGEN_SUPPLY", "default") + ID # must be followed by filter plant id
PRODUCTION_LOSSES = float(getenv_or_exit("HYDROGEN_CELL_" + ID + "_PRODUCTION_LOSSES", 0.0)) # Percent of ressources lost during proccesing

TOPIC_KPI = getenv_or_exit("TOPIC_HYDROGEN_KPI", "default") + ID #topic to post kpis
TOPIC_PLANED_AMOUNT = getenv_or_exit("TOPIC_HYDROGEN_PLANED_AMOUNT", "default") + ID #topic to receive produce planed amount for the next tick

NOMINAL_PERFORMANCE = NOMINAL_HYDROGEN_SUPPLY / NOMINAL_POWER_DEMAND

PLANED_POWER_DEMAND = NOMINAL_POWER_DEMAND
PLANED_FILTERED_WATER_DEMAND = NOMINAL_FILTERED_WATER_DEMAND
PLANED_HYDROGEN_SUPPLY = NOMINAL_HYDROGEN_SUPPLY

POWER_SUPPLIED = 0
FILTERED_WATER_SUPPLIED = 0
HYDROGEN_PRODUCED = 0
TIMESTAMP = 0

STATUS = True
EFFICIENCY = 0
PRODUCTION = 0
CURRENT_PERFORMANCE = 0

POWER_AVAILABLE = False


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

def not_enough_power():
    global POWER_AVAILABLE
    POWER_AVAILABLE = False

def enough_power():
    global POWER_AVAILABLE
    POWER_AVAILABLE = True

def on_message_water_received(client, userdata, msg):
    """
    Callback function that processes messages from the water received topic.
    It processes how much water is received from water pipe and generates the coresponding volume of filtered volume.
    After that publishes it along with the timestamp.
    """
    global state_manager, TIMESTAMP, FILTERED_WATER_SUPPLIED, TOPIC_HYDROGEN_SUPPLY, TOPIC_KPI, ID, HYDROGEN_PRODUCED
    global STATUS, EFFICIENCY, PRODUCTION, CURRENT_PERFORMANCE

    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    FILTERED_WATER_SUPPLIED = payload["amount"]

    # Calculate the amount of filtered water based on supplied water and publish supply msg 
    HYDROGEN_PRODUCED = produce_on_supplied_filtered_water()
    send_supply_msg(client, TOPIC_HYDROGEN_SUPPLY, TIMESTAMP, HYDROGEN_PRODUCED)

    # Calculate the current KPIs and publish them
    calculate_kpis()
    send_kpi_msg(client, TOPIC_KPI, TIMESTAMP, ID, STATUS, EFFICIENCY, PRODUCTION, CURRENT_PERFORMANCE)

    #state_manager.receive_dependency()  # Mark water as received in state manager

def on_message_tick(client, userdata, msg):
    global state_manager, TIMESTAMP, TOPIC_POWER_REQUEST, ID, TOPIC_POWER_RECEIVE, PLANED_POWER_DEMAND

    # get timestamp from tick msg and request power   
    payload = json.loads(msg.payload)
    TIMESTAMP = payload["timestamp"]
    send_request_msg(client, TOPIC_POWER_REQUEST, TIMESTAMP, ID, TOPIC_POWER_RECEIVE, PLANED_POWER_DEMAND)

    #state_manager.receive_tick()

def on_message_power_received(client, userdata, msg):
    """
    Callback function that processes messages from the tick generator topic.
    It publishes topic with request for water and power
    
    Parameters:
    client (MQTT client): The MQTT client instance
    msg (MQTTMessage): The message containing the tick timestamp
    """
    global state_manager, TIMESTAMP
    global TOPIC_FILTERED_WATER_REQUEST, ID, TOPIC_FILTERED_WATER_RECEIVE, POWER_SUPPLIED

    payload = json.loads(msg.payload)
    TIMESTAMP = payload["timestamp"]
    POWER_SUPPLIED = payload["amount"]

    # Calculate filtered water demand based on supplied power and publish filtered water request
    filtered_water_demand = filtered_water_demand_on_supplied_power()
    send_request_msg(client, TOPIC_FILTERED_WATER_REQUEST, TIMESTAMP, ID, TOPIC_FILTERED_WATER_RECEIVE, filtered_water_demand)

    #state_manager.receive_power()

def on_message_plan(client, userdata, msg):
    global PLANED_HYDROGEN_SUPPLY

    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    PLANED_HYDROGEN_SUPPLY = payload["amount"]

    calculate_planed_demand()

def send_request_msg(client, request_topic, timestamp, plant_id, reply_topic, amount):
    data = {
        "timestamp": timestamp, 
        "plant_id": plant_id, 
        "reply_topic": reply_topic, 
        "amount": amount
    }
    client.publish(request_topic, json.dumps(data))

def send_supply_msg(client, supply_topic, timestamp, amount):
    data = {
        "timestamp": timestamp,  
        "amount": amount
    }
    client.publish(supply_topic, json.dumps(data))

def send_kpi_msg(client, kpi_topic, timestamp, plant_id, status, eff, prod, cper):
    data = {
        "timestamp": timestamp, 
        "plant_id": plant_id,
        "status": status,
        "eff": eff, 
        "prod": prod, 
        "cper": cper
    }
    client.publish(kpi_topic, json.dumps(data))

def filtered_water_demand_on_supplied_power():
    global POWER_SUPPLIED, PLANED_POWER_DEMAND, PLANED_FILTERED_WATER_DEMAND

    if POWER_SUPPLIED >= PLANED_POWER_DEMAND:
        filtered_water_demand = PLANED_FILTERED_WATER_DEMAND
    else:
        filtered_water_demand = (POWER_SUPPLIED / PLANED_POWER_DEMAND) * PLANED_FILTERED_WATER_DEMAND

    return filtered_water_demand

def produce_on_supplied_filtered_water():
    global FILTERED_WATER_SUPPLIED, PLANED_FILTERED_WATER_DEMAND, PLANED_HYDROGEN_SUPPLY
    hydrogen = 0

    if FILTERED_WATER_SUPPLIED < PLANED_FILTERED_WATER_DEMAND:
        hydrogen = FILTERED_WATER_SUPPLIED
    else:
        hydrogen = PLANED_FILTERED_WATER_DEMAND
    return hydrogen

def calculate_kpis():
    global EFFICIENCY, PRODUCTION, CURRENT_PERFORMANCE
    global HYDROGEN_PRODUCED, POWER_SUPPLIED, FILTERED_WATER_SUPPLIED, NOMINAL_HYDROGEN_SUPPLY

    EFFICIENCY = HYDROGEN_PRODUCED / POWER_SUPPLIED
    PRODUCTION = HYDROGEN_PRODUCED / FILTERED_WATER_SUPPLIED
    CURRENT_PERFORMANCE = HYDROGEN_PRODUCED / NOMINAL_HYDROGEN_SUPPLY

    return False

def calculate_planed_demand():
    global PLANED_HYDROGEN_SUPPLY, PLANED_FILTERED_WATER_DEMAND, PLANED_POWER_DEMAND, PRODUCTION_LOSSES, NOMINAL_PERFORMANCE 

    PLANED_FILTERED_WATER_DEMAND = PLANED_HYDROGEN_SUPPLY * PRODUCTION_LOSSES

    PLANED_POWER_DEMAND = NOMINAL_PERFORMANCE * PLANED_FILTERED_WATER_DEMAND

def main():
    """
    Main function to initialize the MQTT client, set up subscriptions, 
    and start the message loop.
    """
    
    # Initialize the MQTT client and connect to the broker
    mqtt = MQTTWrapper('mqttbroker', 1883, name='hydrogen_plant_' + ID)
    
    mqtt.subscribe(TICK)
    mqtt.subscribe(TOPIC_FILTERED_WATER_RECEIVE)
    mqtt.subscribe(TOPIC_POWER_RECEIVE)
    mqtt.subscribe(TOPIC_PLANED_AMOUNT)
    mqtt.subscribe_with_callback(TICK, on_message_tick)
    mqtt.subscribe_with_callback(TOPIC_FILTERED_WATER_RECEIVE, on_message_water_received)
    mqtt.subscribe_with_callback(TOPIC_POWER_RECEIVE, on_message_power_received)
    mqtt.subscribe_with_callback(TOPIC_PLANED_AMOUNT, on_message_plan)
    
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
