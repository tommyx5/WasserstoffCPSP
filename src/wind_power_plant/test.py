import sys
import json
import logging
from datetime import datetime
from meteostat import Point, Daily, Hourly
import os
import math
import numpy as np
import matplotlib.pyplot as plt

RS =  287.1 #J/(kg·K)
HEKTO = 100
CELSIUS_IN_KELVIN = 273.15

LATITUDE = 54.9083
LONGITUDE = 8.3180
ALTITUDE = 6
# Create Point for Hamburg Koordinaten: 53° 33′ N, 10° 0′ O 6m
POINT = Point(LATITUDE, LONGITUDE, ALTITUDE)

START_YEAR = 2018
START_MONTH = 1
START_DAY = 1
start = datetime(START_YEAR, START_MONTH, START_DAY)
end = datetime(2022, 12, 31, 23, 59)

# Get daily data for 2018 - 2022
data = Hourly(POINT, start, end)
data = data.fetch()

p = data['pres']
t = data['temp']
s = data['wspd']

p1 = []
for i in range(len(p)):
    p1.append(round((p[i]*HEKTO)/(RS*(t[i]+CELSIUS_IN_KELVIN)), 2))

DATA = [p1,t,s]

LENGTH = len(DATA[0])
POS = 0
COUNT = 0
DIVIDE = 4
NAME = "hamburg"
UPPER_CUT_OUT_WIND_SPEED = 34.0
LOWER_CUT_OUT_WIND_SPEED = 28.0

KMH_IN_MS = 1000/3600
WATT_IN_KILOWATT = 1000
PERCENT = 100
POW2 = 2
POW3 = 3

MODEL = "E126"
ROTOR_DIAMETER = 127.0
AREA = math.pi*math.pow(ROTOR_DIAMETER/2,POW2)
RATED_POWER = 7500.0

CP = [0.0, 0.12,0.29,0.4,0.43,0.46,0.48,0.49,0.5,0.49,0.44,0.39,0.35,0.3,0.26,0.22,0.19,0.16,0.14,0.12,0.1,0.09,0.08,0.07,0.06]

def calc_power(density, windspeed):
    global CP, AREA, RATED_POWER
    power = (0.5*AREA*density*math.pow(windspeed*KMH_IN_MS,POW3)*0.5)/WATT_IN_KILOWATT
    if power > RATED_POWER:
        power = RATED_POWER
    return power

def calc_power_list(data):
    length = len(data[0])
    res = []
    for i in range(length):
        res.append(calc_power(data[0][i], data[2][i]))
    return np.array(res)

def calc_mean(arr):
    return np.mean(arr)

def count_max(arr, maxval):
    count = 0
    for i in range(len(arr)):
        if (arr[i] >= maxval):
            count += 1
    return count
            
def count_min(arr, minval):
    count = 0
    for i in range(len(arr)):
        if (arr[i] <= minval):
            count += 1
    return count

power_list = calc_power_list(DATA)
print(calc_mean(power_list))
print(np.amin(power_list), count_max(power_list, 7500))
print(np.amax(power_list), count_min(power_list, 2300))

print(power_list)
plt.plot(range(len(power_list)),power_list, "red")
plt.show()