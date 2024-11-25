# WasserstoffCPSP
Simulation of hydrogen production plant as part of a praktikum: cyber-physical systems

To start the Application.
Run the "docker compose up" command, then in the browser go to 127.0.0.1:1880/ui adress to see the dashboard.

To add a new container you need to edit compose.yml file, that you can find in the main folder.

The Application uses .env file to store the environmental variables. While adding the new or changing the old code, keep in mind and use it. (The file is in src folder)

# Note
Usefull commands:
docker compose build - to build the container network without runnig it
docker compose down - to remove the container network

To subscribe to all topics that are being published open new console and run [docker exec -it mqttbroker sh -c "mosquitto_sub -v -t '#'"] 

To attach directly to the stdout of a certain container run [docker exec -it <container_name_or_id> /bin/bash] or [docker attach <container_name_or_id>]