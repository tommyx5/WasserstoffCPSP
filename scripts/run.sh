#!/usr/bin/env bash
echo "Create network..."
docker network create cps-net

echo "Starting MQTT Broker..."
docker run -d -p 127.0.0.1:8883:1883 --net=cps-net --name mqttbroker \
  eclipse-mosquitto:1.6.13

echo "Starting dashboard..."
docker run -d -p 127.0.0.1:1880:1880 --net=cps-net --name dashboard dashboard:0.1

echo "Starting Wind Power Plant Sum"
docker run -d --net=cps-net --name wind_power_sum wind_power_sum:0.1

echo "Starting Wind Power Plant ID = 0"
docker run -d --net=cps-net --name wind_power_plant_0 wind_power_plant_0:0.1

echo "Starting Wind Power Plant ID = 1"
docker run -d --net=cps-net --name wind_power_plant_1 wind_power_plant_1:0.1

echo "Starting Climate Generator Hamburg"
docker run -d --net=cps-net --name climate_gen_hamburg climate_gen_hamburg:0.1

echo "Starting Request Hydrogen Generator"
docker run -d --net=cps-net --name request_hydrogen_gen request_hydrogen_gen:0.1

echo "Starting Tick Generator..."
docker run -d --net=cps-net --name tick_gen tick_gen:0.1

