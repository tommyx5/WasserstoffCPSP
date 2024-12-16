import sys
import json
import logging
from random import seed, randint
from mqtt.mqtt_wrapper import MQTTWrapper
import os

TEST = False
TEST_DATA = {"payload": "THIS IS A BASE TEST!"}
TETS_TOPIC = "data/test"

def getenv_or_exit(env_name, default="default"):
    value = os.getenv(env_name, default)
    if value == default:
        raise SystemExit(f"Environment variable {env_name} not set")
    return value

PLANT_DATA = {}
PLANT_DATA["filter"] = {}
PLANT_DATA["hydrogen"] = {}

COUNT_POWER_GEN = int(getenv_or_exit("POWER_SUM_COUNT_POWER_GEN", 0))
COUNT_FILTER_PLANT = int(getenv_or_exit("COUNT_FILTER_PLANT", 0))
COUNT_HYDROGEN_PLANT = int(getenv_or_exit("COUNT_HYDROGEN_PLANT", 0))

TICK = getenv_or_exit('TOPIC_TICK_GEN_TICK', 'default')
TOPIC_ADAPTIVE_MODE = getenv_or_exit('TOPIC_ADAPTIVE_MODE', 'default')
WIND_POWER_SUM_DATA = getenv_or_exit("TOPIC_POWER_SUM_POWER_SUM_DATA", "default")
WIND_POWER_DATA = getenv_or_exit("TOPIC_POWER_PLANT_POWER_DATA", "default")
TOPIC_FILTER_REQUEST = getenv_or_exit("TOPIC_POWER_FILTER_POWER_DATA", "default")
TOPIC_HYDROGEN_REQUEST = getenv_or_exit("TOPIC_POWER_HYDROGEN_POWER_DATA", "default")
TOPIC_FILTER_KPIS = getenv_or_exit("TOPIC_FILTER_KPIS", "default")
TOPIC_HYDROGEN_KPIS = getenv_or_exit("TOPIC_FILTER_KPIS", "default")

WIND_POWER_TOPIC_LIST = []
for i in range(COUNT_POWER_GEN):
    WIND_POWER_TOPIC_LIST.append(WIND_POWER_DATA+str(i))
    
FILTER_PLANT_TOPIC_LIST = []
FILTER_KPIS_TOPIC_LIST = []
for i in range(COUNT_FILTER_PLANT):
    FILTER_PLANT_TOPIC_LIST.append(TOPIC_FILTER_REQUEST+str(i))
    FILTER_KPIS_TOPIC_LIST.append(TOPIC_FILTER_KPIS+str(i))
    PLANT_DATA["filter"][i] = {}
    PLANT_DATA["filter"][i]["reply_topic"] = ""
    PLANT_DATA["filter"][i]["amount"] = ""
    PLANT_DATA["filter"][i]["timestamp"] = 0
    PLANT_DATA["filter"][i]["status"] = True
    PLANT_DATA["filter"][i]["eff"] = 0.5
    PLANT_DATA["filter"][i]["prod"] = 0.5
    PLANT_DATA["filter"][i]["cper"] = 0.5
    PLANT_DATA["filter"][i]["powersupply"] = 0
    PLANT_DATA["filter"][i]["priority"] = 0
    
HYDROGEN_PLANT_TOPIC_LIST = []
HYDROGEN_KPIS_TOPIC_LIST = []
for i in range(COUNT_HYDROGEN_PLANT):
    HYDROGEN_PLANT_TOPIC_LIST.append(TOPIC_HYDROGEN_REQUEST+str(i))
    HYDROGEN_KPIS_TOPIC_LIST.append(TOPIC_FILTER_KPIS+str(i))
    PLANT_DATA["hydrogen"][i] = {}
    PLANT_DATA["hydrogen"][i]["reply_topic"] = ""
    PLANT_DATA["hydrogen"][i]["amount"] = ""
    PLANT_DATA["hydrogen"][i]["timestamp"] = 0
    PLANT_DATA["hydrogen"][i]["status"] = True
    PLANT_DATA["hydrogen"][i]["eff"] = 0.5
    PLANT_DATA["hydrogen"][i]["prod"] = 0.5
    PLANT_DATA["hydrogen"][i]["cper"] = 0.5
    PLANT_DATA["hydrogen"][i]["powersupply"] = 0
    PLANT_DATA["hydrogen"][i]["priority"] = 0

SUM_POWER = 0
AVAILABLE_POWER = SUM_POWER
WEIGHTS = [2/5,2/5,1/5]
COUNT = 0
MEAN_POWER = 0
POWER_LIST = []
COUNT_TICKS_MAX = 24*4
COUNT_TICKS = 0
for i in range(COUNT_TICKS_MAX):
    POWER_LIST.append(0)
ADAPTIVE = False

def main():
    mqtt = MQTTWrapper('mqttbroker', 1883, name='wind_power_sum')   
    mqtt.subscribe(TOPIC_ADAPTIVE_MODE)
    mqtt.subscribe_with_callback(TOPIC_ADAPTIVE_MODE, on_message_adaptive_mode)
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

def calculate_supply():
    global SUM_POWER, MEAN_POWER, AVAILABLE_POWER, PLANT_DATA
    sum_eff = 0
    sum_prod = 0
    sum_cper = 0
    result_list = []
    result_list_hydrogen = [] 
    for typ in PLANT_DATA.keys():
        for id in PLANT_DATA[typ].keys():
            sum_eff += PLANT_DATA[typ][id]["eff"]
            sum_prod += PLANT_DATA[typ][id]["prod"]
            sum_cper += PLANT_DATA[typ][id]["cper"]
    typ = "filter"
    for id in PLANT_DATA[typ].keys():
        PLANT_DATA[typ][id]["priority"] = (PLANT_DATA[typ][id]["eff"]/sum_eff+
                                            PLANT_DATA[typ][id]["prod"]/sum_prod+
                                            PLANT_DATA[typ][id]["cper"]/sum_cper)
        result_list.append([PLANT_DATA[typ][id]["priority"],typ,PLANT_DATA[typ][id],PLANT_DATA[typ][id]["amount"],PLANT_DATA[typ][id]["reply_topic"]])
    result_list.sort(key=get_key,reverse=True)
    typ = "hydrogen"
    for id in PLANT_DATA[typ].keys():      
        PLANT_DATA[typ][id]["priority"] = (PLANT_DATA[typ][id]["eff"]/sum_eff+
                                            PLANT_DATA[typ][id]["prod"]/sum_prod+
                                            PLANT_DATA[typ][id]["cper"]/sum_cper)
        result_list_hydrogen.append([PLANT_DATA[typ][id]["priority"],typ,PLANT_DATA[typ][id],PLANT_DATA[typ][id]["amount"],PLANT_DATA[typ][id]["reply_topic"]])
    result_list_hydrogen.sort(key=get_key,reverse=True)
    
    factor = 1
    multi = 100
    for i in range(len(result_list)+len(result_list_hydrogen)):
        factor *= multi
    calc_factor = factor
    for i in range(len(result_list)):
        result_list[i][0] = result_list[i][0]*(calc_factor)
        calc_factor /= multi
    calc_factor = factor
    for i in range(len(result_list_hydrogen)):
        result_list_hydrogen[i][0] = result_list_hydrogen[i][0]*(calc_factor)
        calc_factor /= multi
    
    result_list.extend(result_list_hydrogen)
    for i in range(len(result_list)):
        if AVAILABLE_POWER - result_list[i][3] > 0:
            AVAILABLE_POWER -= result_list[i][3]
        else:
            result_list[i][3] = 0
    return result_list
    
def on_message_adaptive_mode(client, userdata, msg):
    global ADAPTIVE
    ADAPTIVE = bool(msg.payload.decode("utf-8"))
    if TEST:
        client.publish(TETS_TOPIC, json.dumps({"payload": "on_message_adaptive_mode"}))
    
    
def on_message_power(client, userdata, msg):
    global WIND_POWER_SUM_DATA
    global COUNT, COUNT_TICKS_MAX, COUNT_TICKS
    global SUM_POWER, MEAN_POWER, POWER_LIST, AVAILABLE_POWER
    global COUNT_POWER_GEN

    payload = json.loads(msg.payload) 
    power = payload["power"]
    timestamp = payload["timestamp"]
    
    if COUNT % COUNT_POWER_GEN == 0:
        SUM_POWER = power
    else:
        SUM_POWER += power
        POWER_LIST[COUNT_TICKS] = SUM_POWER
        COUNT_TICKS = (COUNT_TICKS + 1) % COUNT_TICKS_MAX
    if COUNT == COUNT_POWER_GEN-1:
        calc_mean()
        # Extract the timestamp from the tick message and decode it from UTF-8
        data = {"power": SUM_POWER, "mean_power": MEAN_POWER, "timestamp": timestamp}
        # Publish the data to the chaos sensor topic in JSON format
        client.publish(WIND_POWER_SUM_DATA, json.dumps(data))
        AVAILABLE_POWER = SUM_POWER
    COUNT = (COUNT + 1) % COUNT_POWER_GEN
    if TEST:
        client.publish(TETS_TOPIC, json.dumps({"payload": "on_message_power"}))

def on_message_filter_kpi(client, userdata, msg):
    global PLANT_DATA
    payload = json.loads(msg.payload)
    plant_id = payload["plant_id"]
    if not plant_id in PLANT_DATA["filter"].keys():
        PLANT_DATA["filter"][plant_id] = {}
    PLANT_DATA["filter"][plant_id]["status"] = payload["status"]
    PLANT_DATA["filter"][plant_id]["eff"] = payload["eff"]
    PLANT_DATA["filter"][plant_id]["prod"] = payload["prod"]
    PLANT_DATA["filter"][plant_id]["cper"] = payload["cper"]
    if TEST:
        client.publish(TETS_TOPIC, json.dumps({"payload": "on_message_filter_kpi"}))

    
def on_message_hydrogen_kpi(client, userdata, msg):
    global PLANT_DATA
    payload = json.loads(msg.payload)
    plant_id = payload["plant_id"]
    if not plant_id in PLANT_DATA["filter"].keys():
        PLANT_DATA["hydrogen"][plant_id] = {}
    PLANT_DATA["hydrogen"][plant_id]["status"] = payload["status"]
    PLANT_DATA["hydrogen"][plant_id]["eff"] = payload["eff"]
    PLANT_DATA["hydrogen"][plant_id]["prod"] = payload["prod"]
    PLANT_DATA["hydrogen"][plant_id]["cper"] = payload["cper"]
    if TEST:
        client.publish(TETS_TOPIC, json.dumps({"payload": "on_message_hydrogen_kpi"}))
 
def on_message_request(client, userdata, msg):
    global PLANT_DATA, ADAPTIVE, AVAILABLE_POWER
    #extracting the timestamp and other data
    payload = json.loads(msg.payload)
    plant_id = payload["plant_id"]
    plant_type = payload["reply_topic"].split("/")[3]
    ptype = "hydrogen"
    if (plant_type == "filter_plant"):
        ptype = "filter"
    if not plant_id in PLANT_DATA[ptype].keys():
        PLANT_DATA[ptype][plant_id] = {}
    PLANT_DATA[ptype][plant_id]["reply_topic"] = payload["reply_topic"]
    PLANT_DATA[ptype][plant_id]["amount"] = payload["amount"]
    PLANT_DATA[ptype][plant_id]["timestamp"] = payload["timestamp"]
    PLANT_DATA[ptype][plant_id]["powersupply"] = 0

    if ADAPTIVE: #PRIORITY in ratio to eff, prod, cper
        all_request_receiced = True
        for typ in PLANT_DATA.keys():
            for id in PLANT_DATA[typ].keys():
                all_request_receiced = all_request_receiced and (payload["timestamp"] == PLANT_DATA[typ][id]["timestamp"])
        
        if all_request_receiced:
            print(True)
            result_list = calculate_supply()
            for e in result_list:
                data = {
                    "timestamp": payload["timestamp"],
                    "amount": e[3]
                }
                client.publish(e[4], json.dumps(data))
            if TEST:
                client.publish(TETS_TOPIC, json.dumps({"payload": result_list}))
    else: #FIFO
        supplied_power = 0
        if AVAILABLE_POWER - PLANT_DATA[ptype][plant_id]["amount"] > 0:
            AVAILABLE_POWER -= PLANT_DATA[ptype][plant_id]["amount"]
            supplied_power = PLANT_DATA[ptype][plant_id]["amount"]            
        data = {
            "timestamp": payload["timestamp"],
            "amount": supplied_power
        }
        client.publish(payload["reply_topic"], json.dumps(data))


if __name__ == '__main__':
    # Entry point for the script
    main()