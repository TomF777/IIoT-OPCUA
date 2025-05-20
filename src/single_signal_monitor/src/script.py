"""
    Poll data over OPC UA from single sensor(sensor value is FLOAT)
    and store its value and timestamp into InfluxDB.

    The script subscribes to opc NODE_ID (as string)
    and connects to opc ua SERVER_URL (string)
"""

import time
import logging
import os
from datetime import datetime, UTC
from opcua import Client
import influxdb_client
from influxdb_client.client.write_api import WriteOptions



# Set loging system
LOG_FORMAT = "%(levelname)s %(asctime)s \
    Function: %(funcName)s \
    Line: %(lineno)d \
    Message: %(message)s"
logging.getLogger('opcua').setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


def get_env_var(
    env_var: str, req_type=None, default: str | int | float = None
) -> str | int | float:
    """Read env variable and return its required value with log information

    Args:
        env_var (str): Name of environment variable
        req_type (str, int, float): required data type of env variable.
        default (str, int, float): will be returned if is set and env variable does not exist

    Raises:
        SystemExit: Stop program if set type_var has not passed validate
        SystemExit: Stop program if env var does not exist and default is not set
        SystemExit: Stop program if cannot convert env var variable to req_type
    """
    # set local variable. Type and value of read env variable
    env_type = type(env_var)
    env_val = os.getenv(env_var, None)

    # check if input convert type is correct or it is None (if not, return error and stop program)
    allow_convert = [str, int, float]
    if req_type not in allow_convert and req_type is not None:
        logger.error(
            "Cannot convert value of env_var %s to %s. \
                Allowed convert type: str, int, float",
                env_var, req_type
        )
        raise SystemExit

    # Return value of env variable
    if env_val is None and default is None:
        # env_var does not exist and we did not set default value
        logger.error("Env variable %s does not exist", env_var)
        raise SystemExit
    elif env_val is None:
        # env_var does not exist but return default (default is different than none)
        logger.warning(
            "Env variable %s does not exist, return default value: %s",
            env_var, default
        )
        return default
    elif env_type is not req_type and req_type is not None:
        # env var exists and it's type is diffrent as configured
        try:
            converted_env = req_type(env_val)
            logger.info(
                "Env variable %s value: %s. Converted from %s to %s.",
                env_var, env_val, env_type, req_type
            )
            return converted_env
        except Exception as e:
            logger.error(
                "Convert env_var variable %s from %s to %s failed: %s",
                env_var, env_type, req_type, e
            )
            raise SystemExit
    else:
        # env_var exists, is the same type (or we not set type)
        logger.info("Env variable %s value: %s, type: %s",
                    env_var, env_val, env_type)
        return env_val


# Assignment const variable from env or created using env
logger.info("Setting const global variables")

LINE_NAME = get_env_var("LINE_NAME", str)
MACHINE_NAME = get_env_var("MACHINE_NAME", str)
NODE_ID = get_env_var("NODE_ID", str)
SERVER_URL = get_env_var("SERVER_URL", str)

OPCUA_USERNAME = get_env_var("OPCUA_USERNAME", str)
OPCUA_PASSWORD = get_env_var("OPCUA_PASSWORD", str)
OPCUA_SECURE_STRING = get_env_var("OPCUA_SECURE_STRING", str)

INFLUX_HOST = get_env_var("INFLUX_HOST", str)
INFLUX_PORT = get_env_var("INFLUX_PORT", str)
INFLUX_BUCKET_NAME = get_env_var("INFLUX_BUCKET_NAME", str)
INFLUX_BATCH_SIZE = get_env_var("INFLUX_BATCH_SIZE", int)
INFLUX_FLUSH_INTERVAL = get_env_var("INFLUX_FLUSH_INTERVAL", int)
INFLUX_JITTER_INTERVAL = get_env_var("INFLUX_JITTER_INTERVAL", int)
INFLUX_ORG = get_env_var("INFLUX_ORG", str)
INFLUX_TOKEN = get_env_var("INFLUX_TOKEN", str)
INFLUX_URL = "http://" + INFLUX_HOST + ":" + INFLUX_PORT
logger.info("INFLUX_URL value is:  %s", INFLUX_URL)


class OpcHandlerAnalytics:
    """
    Class to handle OPC UA connection and analyse received data from vibration sensor
    """
    def __init__(self, server_url:str):
        self.client = None
        self.node_id =''
        self.server_url = server_url
        logging.info("server opc: %s", self.server_url)

    def connect_to_server(self, username:str, password:str, secure_string:str):
        """
        Connect to OPC UA server using the provided credentials and security string.
        """
        self.client = Client(self.server_url, timeout=60)
        self.client.set_user(username)
        self.client.set_password(password)
        self.client.set_security_string(secure_string)

        while True:
            try:
                self.client.connect()
                logging.info("Connected to OPC Server")
                break
            except Exception as e:
                logging.error("Unable to connect ot OPC server %s", e)
                logging.error(
                    "Trying to re-establish connection with OPC server in 3 seconds "
                )
                time.sleep(3)


    def create_nodes(self, node_id: str):
        """
        Create node references based on the node id as string and will result in
            e.g.:
            self.nodes = {'0': Node(NumericNodeId(ns=2;s=node_string)),
            '1': Node(NumericNodeId(ns=2;s=node_string))}
        """

        if node_id is not None:
            if self.client:
                self.node_id = node_id
                self.node = self.client.get_node(node_id)
                logging.info("Configured node: %s", self.node)
            else:
                logging.error("OPC client is not created!")
        else:
            logging.error("Invalid Node id")


    def read_values(self):
        """
        Read values from the OPC UA server and write them to InfluxDB.
        """

        try:
            # Hold the last time stamp of each sensor value (key:value pair)
            measurement = {}
            while True:

                try:
                    # read opc ua struct
                    opc_node_children = self.node.get_children()

                    line_name     = opc_node_children[0].get_value()
                    machine_name  = opc_node_children[1].get_value()
                    sensor_name   = opc_node_children[2].get_value()
                    sensor_value =  opc_node_children[3].get_value()
                    timestamp     = opc_node_children[4].get_value()
                except Exception as e:
                    logging.error("Error reading node %s || %s: %s",
                                  self.node, opc_node_children, e)
                    continue
                else:

                    # time stamp differs i.e. new data
                    if measurement.get(str(sensor_name)) != timestamp:

                        # data from OPC server valid, store it in InfluxDB
                        self.write_to_influxdb(self,
                                                line_name,
                                                machine_name,
                                                sensor_name,
                                                sensor_value,
                                                timestamp)
                    else:
                        # timestamp same, no new data
                        pass

                    # store the last time stamp of each sensor value
                    measurement.update({str(sensor_name):timestamp})

            # if polling of OPC server is too fast, sleep for a while
            #time.sleep(0.1)

        except KeyboardInterrupt:
            self.client.disconnect()
            logging.info("Keyboard interrupt received. Exiting...")


    def write_to_influxdb(self, *sensor_data):
        """
        Write sensor data to InfluxDB.
        """

        try:
            measurement = "GenericSensor"
            point = (
                influxdb_client.Point(measurement)
                .tag("line_name", str(sensor_data[1]))
                .tag("machine_name", str(sensor_data[2]))
                .tag("sensor_name", str(sensor_data[3]))
                .field("value", float(round(sensor_data[4], 4)))
                .time(time=datetime.fromtimestamp(int(sensor_data[5]) / 1000, UTC),
                    write_precision='ms')
            )
            with influx_client.write_api(write_options=write_options) as write_api:
                write_api.write(INFLUX_BUCKET_NAME, INFLUX_ORG, point)

        except Exception as e:
            logging.error("Send data to InfluxDB failed. Error code/reason: %s", e)



if __name__ == "__main__":

    # Configuring connection with InfluxDB database
    try:
        logger.info("Configuring InfluxDB client ")
        influx_client = influxdb_client.InfluxDBClient(
            url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, enable_gzip=False
        )

        logger.info("Configuring InfluxDB write api")
        write_options = WriteOptions(batch_size=INFLUX_BATCH_SIZE,
                                    flush_interval=INFLUX_FLUSH_INTERVAL,
                                    jitter_interval=INFLUX_JITTER_INTERVAL,
                                    retry_interval=1000)

    except Exception as e:
        logger.error("Configuring InfluxDB failed. Error code/reason: %s", e)


    # Configure connection with OPC UA server
    try:
        opcua_reader = OpcHandlerAnalytics(server_url=SERVER_URL)
        opcua_reader.connect_to_server(
                                        username=OPCUA_USERNAME,
                                        password=OPCUA_PASSWORD,
                                        secure_string=OPCUA_SECURE_STRING
                                    )

        opcua_reader.create_nodes(node_id=NODE_ID)
        opcua_reader.read_values()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Exiting...")
