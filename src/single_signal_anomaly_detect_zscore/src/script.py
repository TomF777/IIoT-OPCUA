"""
    Poll data over OPC UA from single sensor,
    apply z-score anomaly detection algorithm
    on its value and store the results
    and timestamp into InfluxDB.
    The script subscribes to opc NODE_ID (as string)
    and connects to opc ua SERVER_URL (string)
"""
import time
import logging
import os
import statistics
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
                env_var, env_type, req_type
            )
            raise SystemExit
    else:
        # env_var exists, is the same type (or we not set type)
        logger.info("Env variable %s value: %s, type: %s",
                    env_var, env_val, env_type)
        return env_val


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

# Threshold for z-score value. Point above this threshold is treated as anomaly

Z_SCORE_THRESHOLD = get_env_var("Z_SCORE_THRESHOLD", float, default=2.0)

# Number of model points in list to calculate anomaly
MODEL_WINDOW_SIZE = get_env_var("MODEL_WINDOW_SIZE", int, default=50)

# Number of anomaly point in list to calculate anomaly ration
ANOMALY_LIST_SIZE = get_env_var("ANOMALY_LIST_SIZE", int, default=50)


class AnomalyDetectionZscore:
    """
        Analyse real-time data from electrical device
        and apply z-score algorithm to detect anomalies

        model_data          list where real-time (non anomalous) data are stored
        model_size          definition how many data points should be in `model_data`
        anomaly_list        list with anomaly detection results (1 and 0)
        anomaly_list_size  definition how many data points should be in `anomaly_list`
        anomaly_ratio       percentage of anomalous data in `anomaly_list`
        anomaly             result if current data point is anomaly (1) or not (0)
        model_avg           avarage mean of `model_data`
        model_std_dev       standard deviation of `model_data`
        z_score             calculated z-score value for single sensor data
        z_score_thresh      threshold above which sensor data is interpeted as anomalous
        name                name of the object/sensor on which the algorithm is applied
    """

    def __init__(self, name: str,
                 model_size: int, 
                 anomaly_list_size: int, 
                 logger) -> None:
        self._model_data = []
        self._model_size = model_size
        self._anomaly_list = []
        self._anomaly_list_size = anomaly_list_size
        self._anomaly_ratio = 0.0
        self._anomaly = 0
        self._model_avg = 0.0
        self._model_std_dev = 0.0
        self._z_score = 0.0
        self._z_score_thresh = 0.0
        self._name = name
        self._logger = logger

    # Read only wariables
    @property
    def anomaly(self) -> int:
        """return 1 if data point is anmaly, 0 else"""
        return self._anomaly

    @property
    def model_avg(self) -> float:
        """return Mean of sensor data from given data model"""
        return self._model_avg

    @property
    def model_std_dev(self) -> float:
        """return Std Dev of sensor data from given data model"""
        return self._model_std_dev

    @property
    def z_score(self) -> float:
        """return calculated z-score value for given sensor data point"""
        return self._z_score

    @property
    def anomaly_ratio(self) -> float:
        """return anomaly ratio in real-time data"""
        return self._anomaly_ratio

    @property
    def model_completeness(self) -> int:
        """return percentage of data model"""
        return int(100 * len(self._model_data) / self._model_size)

    @property
    def z_score_thresh(self) -> float:
        """return z-score threshold value"""
        return self._z_score_thresh

    @z_score_thresh.setter
    def z_score_thresh(self, z_score_threshold: float):
        if z_score_threshold == 0:
            logger.error("Z-score threshold must be above zero")
            self._z_score_thresh = 2.0
        else:
            self._z_score_thresh = z_score_threshold

    def reset_algorithm(self) -> bool:
        """Reset data model in algorithm"""

        self._model_data = []
        self._anomaly_list = []
        self._anomaly_ratio = 0.0
        self._anomaly = 0
        self._model_avg = 0.0
        self._model_std_dev = 0.0
        self._z_score = 0.0

    def is_model_complete(self) -> bool:
        """Return True if data model has enough data points"""
        return True if len(self._model_data) == self._model_size else False

    def calculate_anomaly_ratio(self):
        """Sum all anomalies results (0 and 1) from `anomaly_list`
           and divide it by the size of the list

        Args:
            anomaly_list_size (int): size of anomaly list to calculate ratio
        """

        try:
            if self.is_model_complete():
                if len(self._anomaly_list) < self._anomaly_list_size:
                    self._anomaly_list.append(self._anomaly)
                else:
                    self._anomaly_list.pop(0)
                    self._anomaly_list.append(self._anomaly)
                    self._anomaly_ratio = round(sum(self._anomaly_list) / self._anomaly_list_size, 3)
        except Exception as e:
            logger.error(
                "Calculation `anomaly ratio of model` %s failed. Error code/reason: %s",
                self._name, e
            )

    def check_if_anomaly(self, value: float):
        """
        Z-score algorithm to check if argument value is anomaly or not.

        Args:
            value (any): input value (sensor data) to be evaluated by algorithm
        """

        try:
            if self.is_model_complete():
                # recalculate the avg and std dev using only data points which are not anomaly
                self._model_avg = round(abs(statistics.mean(self._model_data)), 3)
                self._model_std_dev = abs(statistics.stdev(self._model_data))

                # avoid division by zero
                if self._model_std_dev == 0:
                    self._model_std_dev = 0.001
                self._z_score = round((abs(value) - self._model_avg) / self._model_std_dev, 3)

                # Check if new point is beyond z-score threshold i.e. this is anomaly
                if abs(self._z_score) > self.z_score_thresh:
                    # If anomaly, do not add to the model_data
                    self._anomaly = 1
                else:
                    # If not anomaly, add this point to data model
                    # and delete the 1st point (moving window)
                    self._model_data.pop(0)
                    self._model_data.append(value)
                    self._anomaly = 0

            else:
                # build data model by appending incoming sensor data to the list `model_data`
                self._model_data.append(value)

        except Exception as e:
            logger.error(
                'Calculation `anomaly of model` %s failed. Error code/reason: %s',
                self._name, e
            )

class OpcHandlerAnalytics:
    """
    Class to handle OPC UA connection and data reading.
    """
    def __init__(self, server_url:str): 
        self.client = None
        self.node_id ='' 
        self.server_url = server_url
        logging.info(f"server opc: {self.server_url}")
        self.sensor_analytics = AnomalyDetectionZscore("sensor_analytics", 
                                        MODEL_WINDOW_SIZE, 
                                        ANOMALY_LIST_SIZE, 
                                        logger)

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
                logging.error(f"Unable to connect ot OPC server {e}")
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
                    sensor_value  = opc_node_children[3].get_value()
                    timestamp     = opc_node_children[4].get_value()
                except Exception as e:
                    logging.error("Error reading node %s || %s: %s",
                                  self.node, opc_node_children, e)
                    continue
                else:

                    # time stamp differs i.e. new data
                    if measurement.get(str(sensor_name)) != timestamp:

                        # apply z-score algorithm on received data
                        self.sensor_analytics.z_score_thresh = Z_SCORE_THRESHOLD
                        self.sensor_analytics.check_if_anomaly(sensor_value)
                        self.sensor_analytics.calculate_anomaly_ratio()

                        # Write analytics of sensor data to InfluxDB.
                        self.write_to_influxdb(self,
                                               line_name,
                                               machine_name,
                                               sensor_name,
                                               sensor_value,
                                               self.sensor_analytics.anomaly,
                                               self.sensor_analytics.anomaly_ratio,
                                               self.sensor_analytics.model_avg,
                                               self.sensor_analytics.z_score,
                                               self.sensor_analytics.z_score_thresh,
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
            print("Keyboard interrupt received. Exiting...")


    def write_to_influxdb(self, *sensor_data):
        """
        Write sensor data to InfluxDB.
        """

        try:
            measurement = "SingleSensorAnalytics"
            point = (
                influxdb_client.Point(measurement)
                .tag("line_name", str(sensor_data[1]))
                .tag("machine_name", str(sensor_data[2]))
                .tag("sensor_name", str(sensor_data[3]))
                .field("value", float(round(sensor_data[4], 4)))
                .field("anomaly", int(sensor_data[5]))
                .field("anomaly_ratio", round(float(sensor_data[6]), 4))
                .field("model_avg", round(float(sensor_data[7]), 4))
                .field("z_score", round(float(sensor_data[8]), 4))
                .field("z_score_thresh", round(float(sensor_data[9]), 4))
                .time(time=datetime.fromtimestamp(int(sensor_data[10]) / 1000, UTC),
                    write_precision='ms')
            )

            with influx_client.write_api(write_options=write_options) as write_api:
                write_api.write(INFLUX_BUCKET_NAME, INFLUX_ORG, point)

        except Exception as e:
            logging.error("Send data to InfluxDB failed. Error code/reason: %s", e)


# Main function of script
if __name__ == "__main__":


    # Configure connection with InfluxDB database
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
