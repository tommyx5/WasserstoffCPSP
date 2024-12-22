import sys
import json
from mqtt.mqtt_wrapper import MQTTWrapper
import os
import random

def getenv_or_exit(env_name, default="default"):
    value = os.getenv(env_name, default)
    if value == default:
        raise SystemExit(f"Environment variable {env_name} not set")
    return value

ID = getenv_or_exit("ID", "default")
NOMINAL_WATER_DEMAND = float(getenv_or_exit("FILTER_PLANT_" + ID + "_NOMINAL_WATER_DEMAND", 0.0)) # Water demand at 100% Perfomance (in m^3)
NOMINAL_POWER_DEMAND = float(getenv_or_exit("FILTER_PLANT_" + ID + "_NOMINAL_POWER_DEMAND", 0.0)) # Power demand at 100% Perfomance (in kW)
NOMINAL_FILTERED_WATER_SUPPLY = float(getenv_or_exit("FILTER_PLANT_" + ID + "_NOMINAL_FILTERED_WATER_SUPPLY", 0.0)) # Filtered Water supply at 100% Perfomance (in m^3)
MAXIMAL_WATER_SUPPLY = float(getenv_or_exit("FILTER_PLANT_" + ID + "_MAXIMAL_FILTERED_WATER_SUPPLY", 0.0)) # Filtered Water supply at maximal Perfomance (in m^3)
PRODUCTION_LOSSES = float(getenv_or_exit("FILTER_PLANT_" + ID + "_PRODUCTION_LOSSES", 0.0)) # Percent of ressources lost during proccesing 
STANDART_FAILURE_POSIBILITY = float(getenv_or_exit("FILTER_PLANT_" + ID + "_FAILURE_POSIBILITY", 0.0)) # Posibility of the outage

TICK = getenv_or_exit("TOPIC_TICK_GEN_TICK", "default")
TOPIC_WATER_REQUEST = getenv_or_exit("TOPIC_WATER_PIPE_WATER_REQUEST", "default") # topic to request water
TOPIC_WATER_RECEIVE = getenv_or_exit("TOPIC_FILTER_PLANT_WATER_RECEIVE", "default") + ID # must be followed by filter plant id
TOPIC_POWER_REQUEST = getenv_or_exit("TOPIC_POWER_FILTER_POWER_DATA", "default") + ID  # topic to request power (explicit for filters, must be followed by filter plant id)
TOPIC_POWER_RECEIVE = getenv_or_exit("TOPIC_FILTER_PLANT_POWER_RECEIVE", "default") + ID # must be followed by filter plant id
TOPIC_FILTERED_WATER_SUPPLY = getenv_or_exit("TOPIC_FILTER_PLANT_FILTERED_WATER_SUPPLY", "default") + ID # must be followed by filter plant id
TOPIC_KPI = getenv_or_exit("TOPIC_FILTER_PLANT_KPI", "default") + ID # Topic to post kpis
TOPIC_PLANED_AMOUNT = getenv_or_exit("TOPIC_FILTER_PLANT_PLANED_AMOUNT", "default") + ID # topic to receive produce planed amount for the next tick

TOPIC_FILTERED_WATER_REQUEST = getenv_or_exit("TOPIC_FILTER_PLANT_FILTERED_WATER_REQUEST", "default") + ID # topic to receive requests from filtered water pipe (must be followed by filter plant id)

NOMINAL_PERFORMANCE = NOMINAL_POWER_DEMAND / NOMINAL_FILTERED_WATER_SUPPLY# Performance: kW production per m^3 (in kW/m^3) 

PLANED_POWER_DEMAND = NOMINAL_POWER_DEMAND
PLANED_WATER_DEMAND = NOMINAL_WATER_DEMAND
PLANED_FILTERED_WATER_SUPPLY = NOMINAL_FILTERED_WATER_SUPPLY

POWER_SUPPLIED = 0
WATER_SUPPLIED = 0
FILTERED_WATER_PRODUCED = 0
TIMESTAMP = 0

STATUS = "online"
EFFICIENCY = 0
PRODUCTION = 0
CURRENT_PERFORMANCE = 0

FAILURE_TICK_COUNT = 0
FAILURE_TIMEOUT = 0
STATUS_POWER_NOT_RECEIVED = True
STATUS_WATER_NOT_RECEIVED = True
STATUS_FAILURE = False
CURRENT_FAILURE_POSIBILITY = STANDART_FAILURE_POSIBILITY
MINIMAL_FAILURE_POSIBILITY_CHANGE = 0.005
OVERPRODUCTION_MODE = False

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
    data_KPI = {
        "timestamp": timestamp, 
        "plant_id": plant_id,
        "status": status,
        "eff": eff, 
        "prod": prod, 
        "cper": cper
    }
    client.publish(kpi_topic, json.dumps(data_KPI))

def water_demand_on_supplied_power():
    global POWER_SUPPLIED, PLANED_POWER_DEMAND, PLANED_WATER_DEMAND
    global STATUS_POWER_NOT_RECEIVED

    if POWER_SUPPLIED >= PLANED_POWER_DEMAND:
        water_demand = PLANED_WATER_DEMAND
    elif PLANED_POWER_DEMAND <= 0:
        water_demand = 0
    else:
        water_demand = round(((POWER_SUPPLIED / PLANED_POWER_DEMAND) * PLANED_WATER_DEMAND),4) 

    # Power outage status
    if POWER_SUPPLIED != 0:
        STATUS_POWER_NOT_RECEIVED = False
    elif PLANED_POWER_DEMAND == 0:
        STATUS_POWER_NOT_RECEIVED = False

    return water_demand

def produce_on_supplied_water():
    global WATER_SUPPLIED, PLANED_WATER_DEMAND, PLANED_FILTERED_WATER_SUPPLY, PRODUCTION_LOSSES, NOMINAL_WATER_DEMAND, NOMINAL_FILTERED_WATER_SUPPLY
    global STATUS_WATER_NOT_RECEIVED

    if WATER_SUPPLIED < PLANED_WATER_DEMAND:
        filtered_water = round(((WATER_SUPPLIED * (NOMINAL_WATER_DEMAND / NOMINAL_FILTERED_WATER_SUPPLY)) / PRODUCTION_LOSSES),4)
    else:
        filtered_water = PLANED_FILTERED_WATER_SUPPLY

    # Water outage status
    if WATER_SUPPLIED != 0:
        STATUS_WATER_NOT_RECEIVED = False
    elif PLANED_WATER_DEMAND == 0:
        STATUS_WATER_NOT_RECEIVED = False

    return filtered_water

def calculate_kpis():
    global EFFICIENCY, PRODUCTION, CURRENT_PERFORMANCE, STATUS
    global FILTERED_WATER_PRODUCED, POWER_SUPPLIED, WATER_SUPPLIED, NOMINAL_FILTERED_WATER_SUPPLY
    global STATUS_FAILURE, STATUS_POWER_NOT_RECEIVED, STATUS_WATER_NOT_RECEIVED, OVERPRODUCTION_MODE
    
    # Calculate Efficiency
    if(POWER_SUPPLIED != 0):
        EFFICIENCY = FILTERED_WATER_PRODUCED / POWER_SUPPLIED
    else:
        EFFICIENCY = 0
    
    # Calculate Production
    if(WATER_SUPPLIED != 0):
        PRODUCTION = FILTERED_WATER_PRODUCED / WATER_SUPPLIED
    else:
        PRODUCTION = 0

    # Calculate Current Performance
    CURRENT_PERFORMANCE = FILTERED_WATER_PRODUCED / NOMINAL_FILTERED_WATER_SUPPLY
    # Overproduction
    if CURRENT_PERFORMANCE > 1.0:
        OVERPRODUCTION_MODE = True
    else:
        OVERPRODUCTION_MODE = False

    # Decide status (The order matters!)
    if STATUS_FAILURE:
        STATUS = "offline"
    elif STATUS_POWER_NOT_RECEIVED:
        STATUS = "power not received"
    elif STATUS_WATER_NOT_RECEIVED:
        STATUS = "ressource not received"
    else:
        STATUS = "online"

def calculate_demand():
    global PLANED_FILTERED_WATER_SUPPLY, PLANED_WATER_DEMAND, PLANED_POWER_DEMAND, PRODUCTION_LOSSES, NOMINAL_PERFORMANCE, MAXIMAL_WATER_SUPPLY, NOMINAL_WATER_DEMAND 

    PLANED_WATER_DEMAND = round((PLANED_FILTERED_WATER_SUPPLY * (NOMINAL_WATER_DEMAND/MAXIMAL_WATER_SUPPLY) * PRODUCTION_LOSSES),4)

    PLANED_POWER_DEMAND = round((NOMINAL_PERFORMANCE * PLANED_FILTERED_WATER_SUPPLY),4)

def calculate_outage_risk():
    global CURRENT_FAILURE_POSIBILITY, STANDART_FAILURE_POSIBILITY, STATUS_FAILURE, MINIMAL_FAILURE_POSIBILITY_CHANGE
    global OVERPRODUCTION_MODE

    if not STATUS_FAILURE:
        # check wether the plant is in overproduction mode
        if OVERPRODUCTION_MODE:
            CURRENT_FAILURE_POSIBILITY += MINIMAL_FAILURE_POSIBILITY_CHANGE
        elif CURRENT_FAILURE_POSIBILITY > STANDART_FAILURE_POSIBILITY:
            CURRENT_FAILURE_POSIBILITY -= MINIMAL_FAILURE_POSIBILITY_CHANGE 


def failure_check():
    global STATUS_FAILURE, STANDART_FAILURE_POSIBILITY, CURRENT_FAILURE_POSIBILITY, FAILURE_TICK_COUNT, FAILURE_TIMEOUT

    if STATUS_FAILURE:
        # each tick increase outage tick count
        if FAILURE_TICK_COUNT < FAILURE_TIMEOUT:
            FAILURE_TICK_COUNT += 1
        else:
            FAILURE_TICK_COUNT = 0
            CURRENT_FAILURE_POSIBILITY = STANDART_FAILURE_POSIBILITY
            STATUS_FAILURE = False
    else:
        # decide if the plant is experiencing outage
        rng_value = random.random()
        if rng_value <= CURRENT_FAILURE_POSIBILITY:
            # calculate the time the plant will be out
            FAILURE_TICK_COUNT = 0
            FAILURE_TIMEOUT = int(rng_value * 100) 
            STATUS_FAILURE = True

def on_message_tick(client, userdata, msg):
    """
    Callback function that processes messages from the tick topic.
    It send the request msg for the calculated planed power demand from previous tick
    """
    global TIMESTAMP, TOPIC_POWER_REQUEST, ID, TOPIC_POWER_RECEIVE, PLANED_POWER_DEMAND
    global STATUS_POWER_NOT_RECEIVED, STATUS_WATER_NOT_RECEIVED

    # get timestamp from tick msg and request power
    TIMESTAMP = msg.payload.decode("utf-8")

    # reset the status variables
    STATUS_POWER_NOT_RECEIVED = True
    STATUS_WATER_NOT_RECEIVED = True

    failure_check()

def on_message_power_received(client, userdata, msg):
    """
    Callback function that processes messages from the power received topic.
    It processes how much power is received from power plant and calculates the coresponding volume of water,
    that can be proccessed with this power / was planed as demand.
    After that it publishes the water request msg.
    """
    global TIMESTAMP
    global TOPIC_WATER_REQUEST, ID, TOPIC_WATER_RECEIVE, POWER_SUPPLIED

    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    POWER_SUPPLIED = payload["amount"]

    # Calculate water demand based on supplied power and publish water request
    water_demand = water_demand_on_supplied_power()
    send_request_msg(client, TOPIC_WATER_REQUEST, TIMESTAMP, ID, TOPIC_WATER_RECEIVE, water_demand)

def on_message_water_received(client, userdata, msg):
    """
    Callback function that processes messages from the water received topic.
    It processes how much water is received from water pipe and generates the coresponding volume of filtered volume.
    After that publishes it along with the KPIs.
    """
    global TIMESTAMP, WATER_SUPPLIED, TOPIC_FILTERED_WATER_SUPPLY, TOPIC_KPI, ID, FILTERED_WATER_PRODUCED
    global STATUS, EFFICIENCY, PRODUCTION, CURRENT_PERFORMANCE

    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    WATER_SUPPLIED = payload["amount"]

    # Calculate the amount of filtered water based on supplied water and publish supply msg 
    FILTERED_WATER_PRODUCED = produce_on_supplied_water()
    send_supply_msg(client, TOPIC_FILTERED_WATER_SUPPLY, TIMESTAMP, FILTERED_WATER_PRODUCED)

    # Calculate the current KPIs and publish them
    calculate_kpis()
    send_kpi_msg(
        client=client, 
        kpi_topic=TOPIC_KPI, 
        timestamp=TIMESTAMP, 
        plant_id=ID,
        status=STATUS, 
        eff=EFFICIENCY, 
        prod=PRODUCTION, 
        cper=CURRENT_PERFORMANCE
    )

    # Calculate outage risk for the next tick
    calculate_outage_risk()

def on_message_filtered_water_request(client, userdata, msg):
    global TIMESTAMP, TOPIC_POWER_REQUEST, ID, TOPIC_POWER_RECEIVE, PLANED_POWER_DEMAND, PLANED_FILTERED_WATER_SUPPLY

    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    PLANED_FILTERED_WATER_SUPPLY = payload["amount"]

    calculate_demand()
    
    send_request_msg(client, TOPIC_POWER_REQUEST, TIMESTAMP, ID, TOPIC_POWER_RECEIVE, PLANED_POWER_DEMAND)

def main():
    """
    Main function to initialize the MQTT client, set up subscriptions, 
    and start the message loop.
    """
    
    # Initialize the MQTT client and connect to the broker
    mqtt = MQTTWrapper('mqttbroker', 1883, name='filter_plant_' + ID)
    
    mqtt.subscribe(TICK)
    mqtt.subscribe(TOPIC_POWER_RECEIVE)
    mqtt.subscribe(TOPIC_WATER_RECEIVE)
    mqtt.subscribe(TOPIC_PLANED_AMOUNT)
    mqtt.subscribe(TOPIC_FILTERED_WATER_REQUEST)
    mqtt.subscribe_with_callback(TICK, on_message_tick)
    mqtt.subscribe_with_callback(TOPIC_WATER_RECEIVE, on_message_water_received)
    mqtt.subscribe_with_callback(TOPIC_POWER_RECEIVE, on_message_power_received)
    mqtt.subscribe_with_callback(TOPIC_FILTERED_WATER_REQUEST, on_message_filtered_water_request)
    
    try:
        # Start the MQTT loop to process incoming and outgoing messages
        mqtt.loop_forever()
    except (KeyboardInterrupt, SystemExit):
        mqtt.stop()
        sys.exit("KeyboardInterrupt -- shutdown gracefully.")

if __name__ == '__main__':
    # Entry point for the script
    main()
