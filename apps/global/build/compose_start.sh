#!/bin/bash

title()
{
green=`tput setaf 2`
reset=`tput sgr0`

echo ""
echo ""
echo "${green}**********************$1**********************${reset}"
echo ""
echo ""
sleep 1s 
}

info_flat()
{
green=`tput setaf 2`
reset=`tput sgr0`

echo "${green} $1 ${reset}"
sleep 1s 
}


info_enter()
{
green=`tput setaf 2`
reset=`tput sgr0`

echo ""
echo "${green} $1 ${reset}"
sleep 1s 
}

info_enter "Do you want to deploy Grafana, InfluxDB and Portainer? [Y/N]:"
read stdin

if [[ $stdin == [Nn] ]]; then
    echo "Exiting"
    exit
fi

if [[ $stdin != [YyNn] ]]; then
    echo "Invalid input, exiting"
    exit
fi


title  "DEPLOY PROJECT"

info_enter "Create IOT_Network network"
docker network create IOT_Network

info_enter "Up docker compose with name 'iot-project' "
docker compose -p "iot-project" -f ../global.yml up -d 


######################################################
echo  "!!!!! Deploy completed !!!!!"

sleep 1s

