#!/usr/bin/env bash

echo "Stopping containers..."
docker stop dashboard
docker stop wind_power_sum
docker stop filter_system_sum
docker stop hydrogen_system_sum
docker stop distillation_system_sum
docker stop wind_power_plant_0
docker stop wind_power_plant_1
docker stop climate_gen_hamburg
docker stop request_hydrogen_gen
docker stop tick_gen
docker stop mqttbroker

echo -e "\nRemoving containers and network...\n"
docker rm dashboard
docker rm wind_power_sum
docker rm filter_system_sum
docker rm hydrogen_system_sum
docker rm distillation_system_sum
docker rm wind_power_plant_0
docker rm wind_power_plant_1
docker rm climate_gen_hamburg
docker rm request_hydrogen_gen
docker rm tick_gen
docker rm mqttbroker
docker network rm cps-net
