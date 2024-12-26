import sys
import json
import os
import random
import logging
from mqtt.mqtt_wrapper import MQTTWrapper

# Configure the logger
logging.basicConfig(
    level=logging.INFO,  # Set minimum level to log
    format="%(asctime)s - %(levelname)s - %(message)s",  # Customize the output format
)

def getenv_or_exit(env_name, default="default"):
    value = os.getenv(env_name, default)
    if value == default:
        raise SystemExit(f"Environment variable {env_name} not set")
    return value

ID = getenv_or_exit("ID", "default")
NOMINAL_FILTERED_WATER_DEMAND = float(getenv_or_exit("HYDROGEN_CELL_" + ID + "_NOMINAL_FILTERED_WATER_DEMAND", 0.0)) # Filtered water demand at 100% Perfomance (in m^3)
NOMINAL_POWER_DEMAND = float(getenv_or_exit("HYDROGEN_CELL_" + ID + "_NOMINAL_POWER_DEMAND", 0.0)) # Power demand at 100% Perfomance (in kW)
NOMINAL_HYDROGEN_SUPPLY = float(getenv_or_exit("HYDROGEN_CELL_" + ID + "_NOMINAL_HYDROGEN_SUPPLY", 0.0)) # Hydrogen supply at 100% Perfomance (in m^3)
MAXIMAL_HYDROGEN_SUPPLY = float(getenv_or_exit("HYDROGEN_CELL_" + ID + "_MAXIMAL_HYDROGEN_SUPPLY", 0.0)) # Hydrogen supply at maximal Perfomance (in m^3)
PRODUCTION_LOSSES = float(getenv_or_exit("HYDROGEN_CELL_" + ID + "_PRODUCTION_LOSSES", 0.0)) # Percent of ressources lost during proccesing
STANDART_FAILURE_POSIBILITY = float(getenv_or_exit("HYDROGEN_CELL_" + ID + "_FAILURE_POSIBILITY", 0.0)) # Posibility of the outage

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

FAILURE_TICK_COUNT = 0
FAILURE_TIMEOUT = 0
STATUS_POWER_NOT_RECEIVED = True
STATUS_FILTERED_WATER_NOT_RECEIVED = True
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

def send_kpi_msg(client, kpi_topic, timestamp, plant_id, status, eff, prod, cper, npower, namount):
    data = {
        "timestamp": timestamp, 
        "plant_id": plant_id,
        "status": status,
        "eff": eff, 
        "prod": prod, 
        "cper": cper,
        "npower": npower,
        "namount": namount
    }
    client.publish(kpi_topic, json.dumps(data))

def filtered_water_demand_on_supplied_power():
    global POWER_SUPPLIED, PLANED_POWER_DEMAND, PLANED_FILTERED_WATER_DEMAND
    global STATUS_POWER_NOT_RECEIVED

    if POWER_SUPPLIED >= PLANED_POWER_DEMAND:
        filtered_water_demand = PLANED_FILTERED_WATER_DEMAND
    elif(PLANED_POWER_DEMAND <= 0):
        filtered_water_demand = 0
    else:
        filtered_water_demand = round(((POWER_SUPPLIED / PLANED_POWER_DEMAND) * PLANED_FILTERED_WATER_DEMAND),4) 

    return filtered_water_demand

def produce_on_supplied_filtered_water():
    global FILTERED_WATER_SUPPLIED, PLANED_FILTERED_WATER_DEMAND, PLANED_HYDROGEN_SUPPLY, PRODUCTION_LOSSES, NOMINAL_FILTERED_WATER_DEMAND, NOMINAL_HYDROGEN_SUPPLY
    global STATUS_FILTERED_WATER_NOT_RECEIVED

    if FILTERED_WATER_SUPPLIED < PLANED_FILTERED_WATER_DEMAND:
        hydrogen = round(((FILTERED_WATER_SUPPLIED * (NOMINAL_HYDROGEN_SUPPLY / NOMINAL_FILTERED_WATER_DEMAND)) / PRODUCTION_LOSSES),4)
    else:
        hydrogen = PLANED_HYDROGEN_SUPPLY
    
    # Water outage status
    if FILTERED_WATER_SUPPLIED != 0:
        STATUS_FILTERED_WATER_NOT_RECEIVED = False
    elif PLANED_HYDROGEN_SUPPLY == 0:
        STATUS_FILTERED_WATER_NOT_RECEIVED = False
    
    return hydrogen

def calculate_kpis():
    global EFFICIENCY, PRODUCTION, CURRENT_PERFORMANCE, STATUS
    global HYDROGEN_PRODUCED, POWER_SUPPLIED, FILTERED_WATER_SUPPLIED, NOMINAL_HYDROGEN_SUPPLY
    global STATUS_FAILURE, STATUS_POWER_NOT_RECEIVED, STATUS_FILTERED_WATER_NOT_RECEIVED, OVERPRODUCTION_MODE
    
    # Calculate Efficiency
    if(POWER_SUPPLIED != 0):
        EFFICIENCY = round((HYDROGEN_PRODUCED / POWER_SUPPLIED),4)
    else:
        EFFICIENCY = 0

    # Calculate Production
    if(FILTERED_WATER_SUPPLIED != 0):
        PRODUCTION = round((HYDROGEN_PRODUCED / FILTERED_WATER_SUPPLIED),4)
    else:
        PRODUCTION = 0
    
    # Calculate Current Performance
    CURRENT_PERFORMANCE = round((HYDROGEN_PRODUCED / NOMINAL_HYDROGEN_SUPPLY),4)
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
    elif STATUS_FILTERED_WATER_NOT_RECEIVED:
        STATUS = "ressource not received"
    else:
        STATUS = "online"

def calculate_filtererd_water_demand():
    global PLANED_HYDROGEN_SUPPLY, PLANED_FILTERED_WATER_DEMAND, PLANED_POWER_DEMAND, PRODUCTION_LOSSES, NOMINAL_PERFORMANCE, NOMINAL_FILTERED_WATER_DEMAND, NOMINAL_HYDROGEN_SUPPLY 

    PLANED_FILTERED_WATER_DEMAND = round((PLANED_HYDROGEN_SUPPLY * (NOMINAL_HYDROGEN_SUPPLY / NOMINAL_FILTERED_WATER_DEMAND) * PRODUCTION_LOSSES),4)

    PLANED_POWER_DEMAND = round((NOMINAL_PERFORMANCE * PLANED_HYDROGEN_SUPPLY),4)

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
    global TIMESTAMP

    if STATUS_FAILURE:
        # each tick increase outage tick count
        if FAILURE_TICK_COUNT < FAILURE_TIMEOUT:
            FAILURE_TICK_COUNT += 1
        else:
            FAILURE_TICK_COUNT = 0
            CURRENT_FAILURE_POSIBILITY = STANDART_FAILURE_POSIBILITY
            STATUS_FAILURE = False
            logging.info(f"{TIMESTAMP} The hydrogen plant is back online")
    else:
        # decide if the plant is experiencing outage
        rng_value = random.random()
        if rng_value <= CURRENT_FAILURE_POSIBILITY:
            # calculate the time the plant will be out
            FAILURE_TICK_COUNT = 0
            FAILURE_TIMEOUT = int(rng_value * 100) 
            STATUS_FAILURE = True
            logging.info(f"{TIMESTAMP} The hydrogen plant experienced Failure and will be out for {FAILURE_TIMEOUT} ticks")

def on_message_tick(client, userdata, msg):
    """
    Callback function that processes messages from the tick topic.
    It send the request msg for the calculated planed power demand from previous tick
    """
    global TIMESTAMP, TOPIC_POWER_REQUEST, ID, TOPIC_POWER_RECEIVE, PLANED_POWER_DEMAND
    global STATUS_POWER_NOT_RECEIVED, STATUS_FILTERED_WATER_NOT_RECEIVED

    # get timestamp from tick msg and request power
    TIMESTAMP = msg.payload.decode("utf-8")

    # reset the status variables
    STATUS_POWER_NOT_RECEIVED = True
    STATUS_FILTERED_WATER_NOT_RECEIVED = True

    failure_check()

    logging.debug(f"Received tick message, timestamp: {TIMESTAMP}")

def on_message_power_received(client, userdata, msg):
    """
    Callback function that processes messages from the power received topic.
    It processes how much power is received from power plant and calculates the coresponding volume of water,
    that can be proccessed with this power / was planed as demand.
    After that it publishes the water request msg.
    """
    global TIMESTAMP
    global TOPIC_FILTERED_WATER_REQUEST, ID, TOPIC_FILTERED_WATER_RECEIVE, POWER_SUPPLIED, STATUS_POWER_NOT_RECEIVED, PLANED_POWER_DEMAND

    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    POWER_SUPPLIED = payload["amount"]
    
    # Power outage status
    if POWER_SUPPLIED != 0:
        STATUS_POWER_NOT_RECEIVED = False
    elif PLANED_POWER_DEMAND == 0:
        STATUS_POWER_NOT_RECEIVED = False

    logging.debug(f"Received power message. timestamp: {timestamp}, msg topic: {msg.topic}, supplied power: {POWER_SUPPLIED}")

    # Calculate filtered water demand based on supplied power and publish filtered water request
    filtered_water_demand = filtered_water_demand_on_supplied_power()
    send_request_msg(client, TOPIC_FILTERED_WATER_REQUEST, TIMESTAMP, ID, TOPIC_FILTERED_WATER_RECEIVE, filtered_water_demand)
    logging.debug(f"Sending filtered water request message to filter system. timestamp: {TIMESTAMP}, msg topic: {TOPIC_FILTERED_WATER_REQUEST}, plant id: {ID}, reply topic: {TOPIC_FILTERED_WATER_RECEIVE}, demand: {filtered_water_demand}")

def on_message_water_received(client, userdata, msg):
    """
    Callback function that processes messages from the water received topic.
    It processes how much water is received from water pipe and generates the coresponding volume of filtered volume.
    After that publishes it along with the timestamp.
    """
    global TIMESTAMP, FILTERED_WATER_SUPPLIED, TOPIC_HYDROGEN_SUPPLY, TOPIC_KPI, ID, HYDROGEN_PRODUCED
    global STATUS, EFFICIENCY, PRODUCTION, CURRENT_PERFORMANCE, NOMINAL_POWER_DEMAND, NOMINAL_HYDROGEN_SUPPLY

    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    FILTERED_WATER_SUPPLIED = payload["amount"]
    logging.debug(f"Received filtered water message. timestamp: {timestamp}, msg topic: {msg.topic}, supplied filtered water: {FILTERED_WATER_SUPPLIED}")

    # Calculate the amount of filtered water based on supplied water and publish supply msg 
    HYDROGEN_PRODUCED = produce_on_supplied_filtered_water()
    send_supply_msg(client, TOPIC_HYDROGEN_SUPPLY, TIMESTAMP, HYDROGEN_PRODUCED)
    logging.debug(f"Sending filtered water supply message. timestamp: {TIMESTAMP}, msg topic: {TOPIC_HYDROGEN_SUPPLY}, supply: {HYDROGEN_PRODUCED}")

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
        cper=CURRENT_PERFORMANCE,
        npower=NOMINAL_POWER_DEMAND,
        namount=NOMINAL_HYDROGEN_SUPPLY
    )
    logging.debug(f"Sending kpi message. timestamp: {TIMESTAMP}, msg topic: {TOPIC_KPI}, plant id: {ID}, status: {STATUS}, eff: {EFFICIENCY}, prod: {PRODUCTION}, cper: {CURRENT_PERFORMANCE}, npower: {NOMINAL_POWER_DEMAND}, namount: {NOMINAL_HYDROGEN_SUPPLY}")

    # Calculate outage risk for the next tick
    calculate_outage_risk()
    logging.debug(f"Current outage risk: {CURRENT_FAILURE_POSIBILITY}")

def on_message_hydrogen_request(client, userdata, msg):
    global TIMESTAMP, TOPIC_POWER_REQUEST, ID, TOPIC_POWER_RECEIVE, PLANED_POWER_DEMAND, PLANED_HYDROGEN_SUPPLY

    payload = json.loads(msg.payload)
    timestamp = payload["timestamp"]
    PLANED_HYDROGEN_SUPPLY = payload["amount"]
    logging.debug(f"Received hydrogen request message. timestamp: {timestamp}, msg topic: {msg.topic}, requested amount: {PLANED_HYDROGEN_SUPPLY}")

    calculate_filtererd_water_demand()
    send_request_msg(client, TOPIC_POWER_REQUEST, TIMESTAMP, ID, TOPIC_POWER_RECEIVE, PLANED_POWER_DEMAND)
    logging.debug(f"Sending power request message to power line. timestamp: {TIMESTAMP}, msg topic: {TOPIC_POWER_REQUEST}, plant id: {ID}, reply topic: {TOPIC_POWER_RECEIVE}, demand: {PLANED_POWER_DEMAND}")

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
