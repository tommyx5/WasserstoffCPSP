import sys
import json
import logging
from random import seed, randint
from mqtt.mqtt_wrapper import MQTTWrapper
import os

TEST = False
TEST_DATA = {"payload": "THIS IS A BASE TEST!"}
TETS_TOPIC = "data/power/test"
TOPIC_DEBUG = "mgmt/debug_mode"

def getenv_or_exit(env_name, default="default"):
    value = os.getenv(env_name, default)
    if value == default:
        raise SystemExit(f"Environment variable {env_name} not set")
    return value

PLANT_DATA = {}
FILTER_PLANT = "filter_plant"
HYDROGEN_PLANT = "hydrogen_plant"
PLANT_DATA[FILTER_PLANT] = {}
PLANT_DATA[HYDROGEN_PLANT] = {}

COUNT_POWER_GEN = int(getenv_or_exit("POWER_SUM_COUNT_POWER_GEN", 0))
COUNT_FILTER_PLANT = int(getenv_or_exit("NUMBER_OF_FILTER_PLANTS", 0))
COUNT_HYDROGEN_PLANT = int(getenv_or_exit("NUMBER_OF_HYDROGEN_PLANTS", 0))

TICK = getenv_or_exit('TOPIC_TICK_GEN_TICK', 'default')
TOPIC_ADAPTIVE_MODE = getenv_or_exit('TOPIC_ADAPTIVE_MODE', 'default')
WIND_POWER_SUM_DATA = getenv_or_exit("TOPIC_POWER_SUM_POWER_SUM_DATA", "default")
WIND_POWER_DATA = getenv_or_exit("TOPIC_POWER_PLANT_POWER_DATA", "default")
TOPIC_FILTER_REQUEST = getenv_or_exit("TOPIC_POWER_FILTER_POWER_DATA", "default")
TOPIC_HYDROGEN_REQUEST = getenv_or_exit("TOPIC_POWER_HYDROGEN_POWER_DATA", "default")
TOPIC_FILTER_KPIS = getenv_or_exit("TOPIC_FILTER_KPIS", "default")
TOPIC_HYDROGEN_KPIS = getenv_or_exit("TOPIC_FILTER_KPIS", "default")

WIND_POWER_TOPIC_LIST = []
for j in range(COUNT_POWER_GEN):
    i = str(j)
    WIND_POWER_TOPIC_LIST.append(WIND_POWER_DATA+i)
    
FILTER_PLANT_TOPIC_LIST = []
FILTER_KPIS_TOPIC_LIST = []
for j in range(COUNT_FILTER_PLANT):
    i = str(j)
    FILTER_PLANT_TOPIC_LIST.append(TOPIC_FILTER_REQUEST+i)
    FILTER_KPIS_TOPIC_LIST.append(TOPIC_FILTER_KPIS+i)
    PLANT_DATA[FILTER_PLANT][i] = {}
    PLANT_DATA[FILTER_PLANT][i]["reply_topic"] = ""
    PLANT_DATA[FILTER_PLANT][i]["amount"] = 0
    PLANT_DATA[FILTER_PLANT][i]["timestamp"] = i
    PLANT_DATA[FILTER_PLANT][i]["status"] = "offline"
    PLANT_DATA[FILTER_PLANT][i]["eff"] = 0.5
    PLANT_DATA[FILTER_PLANT][i]["prod"] = 0.5
    PLANT_DATA[FILTER_PLANT][i]["cper"] = 0.5
    PLANT_DATA[FILTER_PLANT][i]["powersupply"] = 0
    PLANT_DATA[FILTER_PLANT][i]["priority"] = 0
    PLANT_DATA[FILTER_PLANT][i]["npower"] = 0
    PLANT_DATA[FILTER_PLANT][i]["namount"] = 0
    
HYDROGEN_PLANT_TOPIC_LIST = []
HYDROGEN_KPIS_TOPIC_LIST = []
for j in range(COUNT_HYDROGEN_PLANT):
    i = str(j)
    HYDROGEN_PLANT_TOPIC_LIST.append(TOPIC_HYDROGEN_REQUEST+i)
    HYDROGEN_KPIS_TOPIC_LIST.append(TOPIC_FILTER_KPIS+i)
    PLANT_DATA[HYDROGEN_PLANT][i] = {}
    PLANT_DATA[HYDROGEN_PLANT][i]["reply_topic"] = ""
    PLANT_DATA[HYDROGEN_PLANT][i]["amount"] = 0
    PLANT_DATA[HYDROGEN_PLANT][i]["timestamp"] = i
    PLANT_DATA[HYDROGEN_PLANT][i]["status"] = "offline"
    PLANT_DATA[HYDROGEN_PLANT][i]["eff"] = 0.5
    PLANT_DATA[HYDROGEN_PLANT][i]["prod"] = 0.5
    PLANT_DATA[HYDROGEN_PLANT][i]["cper"] = 0.5
    PLANT_DATA[HYDROGEN_PLANT][i]["powersupply"] = 0
    PLANT_DATA[HYDROGEN_PLANT][i]["priority"] = 0
    PLANT_DATA[HYDROGEN_PLANT][i]["npower"] = 0
    PLANT_DATA[HYDROGEN_PLANT][i]["namount"] = 0

SUM_POWER = 0
POWER_COLLECTED = False
WEIGHTS = [2/5,2/5,1/5]
COUNT = 0
MEAN_POWER = 0
POWER_LIST = []
COUNT_TICKS_MAX = 24*4
COUNT_TICKS = 0
for i in range(COUNT_TICKS_MAX):
    POWER_LIST.append(0)
ADAPTIVE = False
FILTER_RATIO = 0.3 #FILTER_SUM_AMOUNT/(FILTER_SUM_AMOUNT+HYDROGEN_SUM_AMOUNT)
HYDROGEN_RATIO = 1-FILTER_RATIO #HYDROGEN_SUM_AMOUNT/(FILTER_SUM_AMOUNT+HYDROGEN_SUM_AMOUNT)
FILTER_SUM_AMOUNT = 0
HYDROGEN_SUM_AMOUNT = 0
FILTER_AVAILABLE_POWER = SUM_POWER*FILTER_RATIO
HYDROGEN_AVAILABLE_POWER = SUM_POWER*HYDROGEN_RATIO

def on_message_debug_mode(client, userdata, msg):
    global TEST
    boolean = msg.payload.decode("utf-8")
    if boolean == "true" or boolean == "1" or boolean == "I love Python" or boolean == "True":
        TEST = True
    else:
        TEST = False

#MAIN
def main():
    mqtt = MQTTWrapper('mqttbroker', 1883, name='wind_power_sum')   
    mqtt.subscribe(TOPIC_ADAPTIVE_MODE)
    mqtt.subscribe_with_callback(TOPIC_ADAPTIVE_MODE, on_message_adaptive_mode)
    mqtt.subscribe(TOPIC_DEBUG)
    mqtt.subscribe_with_callback(TOPIC_DEBUG, on_message_debug_mode)
    for topic in WIND_POWER_TOPIC_LIST:
        mqtt.subscribe(topic)
        mqtt.subscribe_with_callback(topic, on_message_power)
    for topic in FILTER_PLANT_TOPIC_LIST:
        mqtt.subscribe(topic)
        mqtt.subscribe_with_callback(topic, on_message_request)
    for topic in HYDROGEN_PLANT_TOPIC_LIST:
        mqtt.subscribe(topic)
        mqtt.subscribe_with_callback(topic, on_message_request)
    for topic in FILTER_KPIS_TOPIC_LIST:
        mqtt.subscribe(topic)
        mqtt.subscribe_with_callback(topic, on_message_filter_kpi)
    for topic in HYDROGEN_KPIS_TOPIC_LIST:
        mqtt.subscribe(topic)
        mqtt.subscribe_with_callback(topic, on_message_hydrogen_kpi)
    
    try:
        mqtt.loop_forever()
    except (KeyboardInterrupt, SystemExit):
        mqtt.stop()
        sys.exit("KeyboardInterrupt -- shutdown gracefully.")

def calc_mean():
    global SUM_POWER, MEAN_POWER, POWER_LIST
    summe = 0
    count = 0
    for i in range(COUNT_TICKS_MAX):
        if POWER_LIST[i] > 0:
            summe += POWER_LIST[i]
            count += 1
    if count > 0:
        MEAN_POWER = round(summe / count, 2)
    else:
        MEAN_POWER = 0

def get_key(liste):
    return liste[0]

def calculate_supply(typ, sortByPrio = False):
    global PLANT_DATA
    global HYDROGEN_PLANT, HYDROGEN_AVAILABLE_POWER, HYDROGEN_SUM_AMOUNT, HYDROGEN_RATIO
    global FILTER_PLANT, FILTER_AVAILABLE_POWER, FILTER_SUM_AMOUNT, FILTER_RATIO
    result_list = []
    for id in PLANT_DATA[typ].keys():
        result_list.append([PLANT_DATA[typ][id]["priority"],typ,id,PLANT_DATA[typ][id]["amount"],PLANT_DATA[typ][id]["reply_topic"]])
    if sortByPrio:
        result_list.sort(key=get_key,reverse=True)
    if typ == FILTER_PLANT:
        for e in result_list:
            FILTER_SUM_AMOUNT += e[3]
            if FILTER_AVAILABLE_POWER - e[3] >= 0:
                FILTER_AVAILABLE_POWER = FILTER_AVAILABLE_POWER - e[3]
            else:
                e[3] = 0 
        if FILTER_SUM_AMOUNT+HYDROGEN_SUM_AMOUNT > 0:
            FILTER_RATIO = FILTER_SUM_AMOUNT/(FILTER_SUM_AMOUNT+HYDROGEN_SUM_AMOUNT)
            HYDROGEN_RATIO = HYDROGEN_SUM_AMOUNT/(FILTER_SUM_AMOUNT+HYDROGEN_SUM_AMOUNT)
    if typ == HYDROGEN_PLANT:
        for e in result_list:
            HYDROGEN_SUM_AMOUNT += e[3]
            if HYDROGEN_AVAILABLE_POWER - e[3] >= 0:
                HYDROGEN_AVAILABLE_POWER = HYDROGEN_AVAILABLE_POWER - e[3]
            else:
                e[3] = 0 
    return result_list
    
def on_message_adaptive_mode(client, userdata, msg):
    global ADAPTIVE
    boolean = msg.payload.decode("utf-8")
    if boolean == "true" or boolean == "1" or boolean == "I love Python" or boolean == "True":
        ADAPTIVE = True
    else:
        ADAPTIVE = False
    
    
def on_message_power(client, userdata, msg):
    global WIND_POWER_SUM_DATA
    global COUNT, COUNT_TICKS_MAX, COUNT_TICKS
    global SUM_POWER, MEAN_POWER, POWER_LIST, FILTER_AVAILABLE_POWER, HYDROGEN_AVAILABLE_POWER, POWER_COLLECTED
    global COUNT_POWER_GEN

    payload = json.loads(msg.payload) 
    power = payload["power"]
    timestamp = payload["timestamp"]
    
    if COUNT % COUNT_POWER_GEN == 0:
        SUM_POWER = power
        POWER_COLLECTED = False
    else:
        SUM_POWER += power
        POWER_LIST[COUNT_TICKS] = SUM_POWER
        COUNT_TICKS = (COUNT_TICKS + 1) % COUNT_TICKS_MAX
    if COUNT == COUNT_POWER_GEN-1:
        calc_mean()
        # Extract the timestamp from the tick message and decode it from UTF-8
        data = {"power": round(SUM_POWER,2), "mean_power": MEAN_POWER, "timestamp": timestamp}
        # Publish the data to the chaos sensor topic in JSON format
        client.publish(WIND_POWER_SUM_DATA, json.dumps(data))
        FILTER_AVAILABLE_POWER = SUM_POWER*FILTER_RATIO
        HYDROGEN_AVAILABLE_POWER = SUM_POWER*HYDROGEN_RATIO
        POWER_COLLECTED = True
        if TEST:
            client.publish(TETS_TOPIC, json.dumps({"FILTER_AVAILABLE_POWER": FILTER_AVAILABLE_POWER,"HYDROGEN_AVAILABLE_POWER": HYDROGEN_AVAILABLE_POWER}))
            client.publish(TETS_TOPIC, json.dumps({"FILTER_RATIO": FILTER_RATIO,"HYDROGEN_RATIO": HYDROGEN_RATIO}))
    COUNT = (COUNT + 1) % COUNT_POWER_GEN

def on_message_filter_kpi(client, userdata, msg):
    global PLANT_DATA
    payload = json.loads(msg.payload)
    plant_id = payload["plant_id"]
    if not plant_id in PLANT_DATA[FILTER_PLANT].keys():
        PLANT_DATA[FILTER_PLANT][plant_id] = {}
    PLANT_DATA[FILTER_PLANT][plant_id]["status"] = payload["status"]
    PLANT_DATA[FILTER_PLANT][plant_id]["eff"] = payload["eff"]
    PLANT_DATA[FILTER_PLANT][plant_id]["prod"] = payload["prod"]
    PLANT_DATA[FILTER_PLANT][plant_id]["cper"] = payload["cper"]
    #TODO if implementet, if "namount" in payload and "npower" in payload: can be removed
    if "namount" in payload and "npower" in payload:
        PLANT_DATA[FILTER_PLANT][plant_id]["namount"] = payload["namount"]
        PLANT_DATA[FILTER_PLANT][plant_id]["npower"] = payload["npower"]
        if payload["npower"] > 0:
            PLANT_DATA[FILTER_PLANT][plant_id]["priority"] = payload["namount"]/payload["npower"]
    
def on_message_hydrogen_kpi(client, userdata, msg):
    global PLANT_DATA
    payload = json.loads(msg.payload)
    plant_id = payload["plant_id"]
    if not plant_id in PLANT_DATA[FILTER_PLANT].keys():
        PLANT_DATA[HYDROGEN_PLANT][plant_id] = {}
    PLANT_DATA[HYDROGEN_PLANT][plant_id]["status"] = payload["status"]
    PLANT_DATA[HYDROGEN_PLANT][plant_id]["eff"] = payload["eff"]
    PLANT_DATA[HYDROGEN_PLANT][plant_id]["prod"] = payload["prod"]
    PLANT_DATA[HYDROGEN_PLANT][plant_id]["cper"] = payload["cper"]
    #TODO if implementet, if "namount" in payload and "npower" in payload: can be removed
    if "namount" in payload and "npower" in payload:
        PLANT_DATA[HYDROGEN_PLANT][plant_id]["namount"] = payload["namount"]
        PLANT_DATA[HYDROGEN_PLANT][plant_id]["npower"] = payload["npower"]
        if payload["npower"] > 0:
            PLANT_DATA[HYDROGEN_PLANT][plant_id]["priority"] = payload["namount"]/payload["npower"]
 
def on_message_request(client, userdata, msg):
    global PLANT_DATA, ADAPTIVE, FILTER_PLANT, HYDROGEN_PLANT
    #extracting the timestamp and other data
    payload = json.loads(msg.payload)
    plant_id = payload["plant_id"]
    plant_typ = FILTER_PLANT
    if payload["reply_topic"].split("/")[3] == HYDROGEN_PLANT:
        plant_typ = HYDROGEN_PLANT
    if not plant_id in PLANT_DATA[plant_typ].keys():
        PLANT_DATA[plant_typ][plant_id] = {}
    PLANT_DATA[plant_typ][plant_id]["reply_topic"] = payload["reply_topic"]
    PLANT_DATA[plant_typ][plant_id]["amount"] = payload["amount"]
    PLANT_DATA[plant_typ][plant_id]["timestamp"] = payload["timestamp"]
    PLANT_DATA[plant_typ][plant_id]["powersupply"] = 0
    all_request_receiced = True
    for id in PLANT_DATA[plant_typ].keys():
        all_request_receiced = all_request_receiced and (payload["timestamp"] == PLANT_DATA[plant_typ][id]["timestamp"])
    if all_request_receiced:
        result_list = calculate_supply(plant_typ, sortByPrio=ADAPTIVE)
        send_supply_msg(client, result_list, payload["timestamp"])
        if TEST:
            client.publish(TETS_TOPIC, json.dumps({"SUPPLY_LIST": result_list}))

def send_supply_msg(client, result_list, timestamp):
    global PLANT_DATA, FILTER_SUM_AMOUNT, FILTER_PLANT
    for e in result_list:
        if e[4] != "":
            data = {
                "timestamp": timestamp,
                "amount": e[3]
            }
            client.publish(e[4], json.dumps(data))
            PLANT_DATA[e[1]][e[2]]["timestamp"] = 0

if __name__ == '__main__':
    # Entry point for the script
    main()