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
NOMINAL_FILTERED_WATER_DEMAND = float(getenv_or_exit("HYDROGEN_CELL_" + ID + "_DISTILLED_WATER_DEMAND", 0.0)) # in m^3
NOMINAL_POWER_DEMAND = float(getenv_or_exit("HYDROGEN_CELL_" + ID + "_POWER_DEMAND", 0.0)) # in kW
NOMINAL_HYDROGEN_SUPPLY = float(getenv_or_exit("HYDROGEN_CELL_" + ID + "_HYDROGEN_MAX_SUPPLY", 0.0)) # in m^3
PRODUCTION_LOSSES = float(getenv_or_exit("HYDROGEN_CELL_" + ID + "_PRODUCTION_LOSSES", 0.0)) # Percent of ressources lost during proccesing

TICK = getenv_or_exit("TOPIC_TICK_GEN_TICK", "default")
TOPIC_FILTERED_WATER_REQUEST = getenv_or_exit("TOPIC_FILTER_SUM_FILTERED_WATER_REQUEST", "default") # topic to request water
TOPIC_FILTERED_WATER_RECEIVE = getenv_or_exit("TOPIC_HYDROGEN_CELL_FILTERED_WATER_RECEIVE", "default") + ID # must be followed by filter plant id
TOPIC_POWER_REQUEST = getenv_or_exit("TOPIC_POWER_HYDROGEN_POWER_DATA", "default") + ID  # topic to request power (explicit for hydrogen, must be followed by hydrogen plant id)
TOPIC_POWER_RECEIVE = getenv_or_exit("TOPIC_HYDROGEN_CELL_POWER_RECEIVE", "default") + ID # must be followed by filter plant id
TOPIC_HYDROGEN_SUPPLY = getenv_or_exit("TOPIC_HYDROGEN_CELL_HYDROGEN_SUPPLY", "default") + ID # must be followed by filter plant id
TOPIC_KPI = getenv_or_exit("TOPIC_HYDROGEN_CELL_KPI", "default") + ID #topic to post kpis

TOPIC_HYDROGEN_REQUEST = getenv_or_exit("TOPIC_HYDROGEN_CELL_HYDROGEN_REQUEST", "default") + ID # topic to receive requests from hydrogen pipe (must be followed by filter plant id)

NOMINAL_PERFORMANCE = NOMINAL_POWER_DEMAND / NOMINAL_HYDROGEN_SUPPLY

PLANED_POWER_DEMAND = NOMINAL_POWER_DEMAND
PLANED_FILTERED_WATER_DEMAND = NOMINAL_FILTERED_WATER_DEMAND
PLANED_HYDROGEN_SUPPLY = NOMINAL_HYDROGEN_SUPPLY

POWER_SUPPLIED = 0
FILTERED_WATER_SUPPLIED = 0
HYDROGEN_PRODUCED = 0
TIMESTAMP = 0

STATUS = "online"
EFFICIENCY = 0
PRODUCTION = 0
CURRENT_PERFORMANCE = 0

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
    elif(PLANED_POWER_DEMAND <= 0):
        filtered_water_demand = 0
    else:
        filtered_water_demand = (POWER_SUPPLIED / PLANED_POWER_DEMAND) * PLANED_FILTERED_WATER_DEMAND

    return filtered_water_demand

def produce_on_supplied_filtered_water():
    global FILTERED_WATER_SUPPLIED, PLANED_FILTERED_WATER_DEMAND, PLANED_HYDROGEN_SUPPLY, PRODUCTION_LOSSES, NOMINAL_FILTERED_WATER_DEMAND, NOMINAL_HYDROGEN_SUPPLY
    hydrogen = 0

    if FILTERED_WATER_SUPPLIED < PLANED_FILTERED_WATER_DEMAND:
        hydrogen = (FILTERED_WATER_SUPPLIED * (NOMINAL_HYDROGEN_SUPPLY / NOMINAL_FILTERED_WATER_DEMAND)) / PRODUCTION_LOSSES
    else:
        hydrogen = PLANED_HYDROGEN_SUPPLY
    return hydrogen

def calculate_kpis():
    global EFFICIENCY, PRODUCTION, CURRENT_PERFORMANCE
    global HYDROGEN_PRODUCED, POWER_SUPPLIED, FILTERED_WATER_SUPPLIED, NOMINAL_HYDROGEN_SUPPLY

    if(POWER_SUPPLIED != 0):
        EFFICIENCY = HYDROGEN_PRODUCED / POWER_SUPPLIED
    else:
        EFFICIENCY = 0
    if(FILTERED_WATER_SUPPLIED != 0):
        PRODUCTION = HYDROGEN_PRODUCED / FILTERED_WATER_SUPPLIED
    else:
        PRODUCTION = 0
    CURRENT_PERFORMANCE = HYDROGEN_PRODUCED / NOMINAL_HYDROGEN_SUPPLY

def calculate_filtererd_water_demand():
    global PLANED_HYDROGEN_SUPPLY, PLANED_FILTERED_WATER_DEMAND, PLANED_POWER_DEMAND, PRODUCTION_LOSSES, NOMINAL_PERFORMANCE, NOMINAL_FILTERED_WATER_DEMAND, NOMINAL_HYDROGEN_SUPPLY 

    PLANED_FILTERED_WATER_DEMAND = round((PLANED_HYDROGEN_SUPPLY * (NOMINAL_FILTERED_WATER_DEMAND/NOMINAL_HYDROGEN_SUPPLY) * PRODUCTION_LOSSES),2)

    PLANED_POWER_DEMAND = NOMINAL_PERFORMANCE * PLANED_HYDROGEN_SUPPLY

def on_message_tick(client, userdata, msg):
    global TIMESTAMP

    # get timestamp from tick msg and request power   
    TIMESTAMP = msg.payload.decode("utf-8")

def on_message_power_received(client, userdata, msg):
    global TIMESTAMP
    global TOPIC_FILTERED_WATER_REQUEST, ID, TOPIC_FILTERED_WATER_RECEIVE, POWER_SUPPLIED

    payload = json.loads(msg.payload)
    TIMESTAMP = payload["timestamp"]
    POWER_SUPPLIED = payload["amount"]

    # Calculate filtered water demand based on supplied power and publish filtered water request
    filtered_water_demand = filtered_water_demand_on_supplied_power()
    send_request_msg(client, TOPIC_FILTERED_WATER_REQUEST, TIMESTAMP, ID, TOPIC_FILTERED_WATER_RECEIVE, filtered_water_demand)

def on_message_water_received(client, userdata, msg):
    """
    Callback function that processes messages from the water received topic.
    It processes how much water is received from water pipe and generates the coresponding volume of filtered volume.
    After that publishes it along with the timestamp.
    """
    global TIMESTAMP, FILTERED_WATER_SUPPLIED, TOPIC_HYDROGEN_SUPPLY, TOPIC_KPI, ID, HYDROGEN_PRODUCED
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

def on_message_hydrogen_request(client, userdata, msg):
    global TIMESTAMP, TOPIC_POWER_REQUEST, ID, TOPIC_POWER_RECEIVE, PLANED_POWER_DEMAND, PLANED_HYDROGEN_SUPPLY

    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    PLANED_HYDROGEN_SUPPLY = payload["amount"]

    calculate_filtererd_water_demand()
    
    send_request_msg(client, TOPIC_POWER_REQUEST, TIMESTAMP, ID, TOPIC_POWER_RECEIVE, PLANED_POWER_DEMAND)

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
    mqtt.subscribe(TOPIC_HYDROGEN_REQUEST)
    mqtt.subscribe_with_callback(TICK, on_message_tick)
    mqtt.subscribe_with_callback(TOPIC_FILTERED_WATER_RECEIVE, on_message_water_received)
    mqtt.subscribe_with_callback(TOPIC_POWER_RECEIVE, on_message_power_received)
    mqtt.subscribe_with_callback(TOPIC_HYDROGEN_REQUEST, on_message_hydrogen_request)
    
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
