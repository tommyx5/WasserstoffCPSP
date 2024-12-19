
def get_key(liste):
    return liste[0]

PLANT_DATA = {}
PLANT_DATA["filter"] = {}

timestamp = 2000
status = True # topic to publish the supplied power to
eff = 0.78
prod = 0.8
cper = 0.89

for i in range(0,10):
    timestamp = timestamp*2
    status = True # topic to publish the supplied power to
    eff = eff*2
    prod = prod*2
    cper = cper*2
    PLANT_DATA["filter"][i] = {}
    PLANT_DATA["filter"][i]["timestamp"] = timestamp
    PLANT_DATA["filter"][i]["status"] = status
    PLANT_DATA["filter"][i]["eff"] = eff
    PLANT_DATA["filter"][i]["prod"] = prod
    PLANT_DATA["filter"][i]["cper"] = cper

result_list = []

for typ in PLANT_DATA.keys():
    for id in PLANT_DATA[typ].keys():
        result_list.append([PLANT_DATA[typ][id]["timestamp"],id])
print(result_list)
result_list.sort(key=get_key,reverse=True)
print(result_list)

print(result_list[0])
print(result_list[0][0])
result_list[0][0] = 0
print(result_list[0])

replay_topic = "data/power/supply/hydrogen_plant/"

plant_type = replay_topic.split("/")[3]
ptype = "hydrogen"
if (plant_type == "filter_plant"):
    ptype = "filter"

print(ptype)

c = 1.0
for i in range(1,100):
    print(c,len(str(c)),i)
    c *= 100