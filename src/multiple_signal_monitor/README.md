## Multiple signal monitor

This script polls data over OPC UA from mutliple sensors(sensor value is FLOAT)
and store its value and timestamp into InfluxDB.
Configuration of namespaces, nodes_id and opc ua server url are in `config.json` file.


It expects following data structure for each NODE_ID:
* line_name `(string)`
* machine_name `(string)`
* sensor_name `(string)`
* sensor_value `(float)`
* timestamp `(ulint) - as Epoch Unix (13 digits)`


Examples of air sensor data are depicted on the below screens: 
![signals in grafana](doc/multiple_signal_ex1.png)

