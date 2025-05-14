## Air valve travel time anomaly detection with z-score algorithm 

Script reads air valve travel times over OPC UA,
calculates anomaly using z-score method and stores results to InfluxDB

The script polls opc ua NODE_ID (as string) and connects to opc ua SERVER_URL (string).

It expects following data structure in NODE_ID:
* line_name `(string)`
* machine_name `(string)`
* valve_name `(string)`
* time_type `(string) e.g. Extend/Retract`
* time_value `(int) - in miliseconds`
* timestamp `(ulint) - as Epoch Unix (13 digits)`

