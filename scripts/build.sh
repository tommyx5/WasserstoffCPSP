#!/usr/bin/env bash
BASE_DIR="$( cd -- "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )/../src/"

docker build ${BASE_DIR}tick_gen -t tick_gen:0.1
echo -e "\n\n"

docker build ${BASE_DIR}wind_power_sum -t wind_power_sum:0.1
echo -e "\n\n"

docker build ${BASE_DIR}wind_power_plant_0 -t wind_power_plant_0:0.1
echo -e "\n\n"

docker build ${BASE_DIR}wind_power_plant_1 -t wind_power_plant_1:0.1
echo -e "\n\n"

docker build ${BASE_DIR}climate_gen_hamburg -t climate_gen_hamburg:0.1
echo -e "\n\n"

docker build ${BASE_DIR}request_hydrogen_gen -t request_hydrogen_gen:0.1
echo -e "\n\n"

docker build ${BASE_DIR}dashboard -t dashboard:0.1
echo -e "\n\n"
