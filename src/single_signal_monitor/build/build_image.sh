#!bin/bash

sudo docker build --build-arg date=$(date -u +'%Y-%m-%dT%H:%M:%SZ') --tag generic_single_signal_monitor_opcua_img:0.0.1 ../. 
