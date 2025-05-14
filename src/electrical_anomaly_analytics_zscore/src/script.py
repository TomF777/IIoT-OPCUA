"""
    Poll data from one electrical device over OPC UA.
    It calculates analytics like definite integral over fixed time,
    electrical current assymetry and inrush current.
    Anomaly detection algorithm is then applied to
    integral value and inrush current.
    Analytics results and timestamp are saved in InfluxDB.
    It also stores raw electrical data to InfluxDB.

    The script subscribes to opc NODE_ID (as string)
    and connects to opc ua SERVER_URL (string)
"""

import logging
import time
from datetime import datetime, UTC
from opcua import Client
import influxdb_client
from influxdb_client.client.write_api import WriteOptions
from scipy.signal import find_peaks
from helper import AnomalyDetectionZscore, ElectricalAnalytics, get_env_var

# Set up logging configuration
LOG_FORMAT = "%(levelname)s %(asctime)s \
    Function: %(funcName)s \
    Line: %(lineno)d \
    Message: %(message)s"
logging.getLogger('opcua').setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


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
logger.info(f"INFLUX_URL value is:  {INFLUX_URL} ")

# which current peak in a row should be taken into inrush current detection
CURRENT_PEAK_NUMBER = get_env_var("CURRENT_PEAK_NUMBER", int, default=1)

# electrical current threshold for peak detection algorithm
CURRENT_PEAK_HEIGHT = get_env_var("CURRENT_PEAK_HEIGHT", float, default=1.0)

#Threshold for z-score value. Point above this threshold is treated as anomaly
Z_SCORE_THRESHOLD = get_env_var("Z_SCORE_THRESHOLD", float, default=2.0)

# number of model points in a list to calculate anomaly
MODEL_WINDOW_SIZE = get_env_var("MODEL_WINDOW_SIZE", int, default=25)

# number of anomaly points in a list to calculate anomaly ratio
ANOMALY_LIST_SIZE = get_env_var("ANOMALY_LIST_SIZE", int, default=25)


class OpcHandlerAnalytics:
    """
    Class to handle OPC UA connection and analyse received data from electrical device
    """
    def __init__(self, server_url:str):
        self.client = None
        self.node_id =''
        self.server_url = server_url
        self.el_current_integr_ph1_analytics =AnomalyDetectionZscore(
                                                "el_current_integr_ph1_analytics",
                                                MODEL_WINDOW_SIZE,
                                                ANOMALY_LIST_SIZE,
                                                logger)

        self.el_current_integr_ph2_analytics = AnomalyDetectionZscore(
                                                "el_current_integr_ph2_analytics",
                                                MODEL_WINDOW_SIZE,
                                                ANOMALY_LIST_SIZE,
                                                logger)

        self.el_current_integr_ph3_analytics = AnomalyDetectionZscore(
                                                "el_current_integr_ph3_analytics",
                                                MODEL_WINDOW_SIZE,
                                                ANOMALY_LIST_SIZE,
                                                logger)

        self.el_inrush_current_ph1_analytics = AnomalyDetectionZscore(
                                                "el_inrush_current_ph1_analytics",
                                                MODEL_WINDOW_SIZE,
                                                ANOMALY_LIST_SIZE,
                                                logger)

        self.el_inrush_current_ph2_analytics = AnomalyDetectionZscore(
                                                "el_inrush_current_ph2_analytics",
                                                MODEL_WINDOW_SIZE,
                                                ANOMALY_LIST_SIZE,
                                                logger)

        self.el_inrush_current_ph3_analytics = AnomalyDetectionZscore(
                                                "el_inrush_current_ph3_analytics",
                                                MODEL_WINDOW_SIZE,
                                                ANOMALY_LIST_SIZE,
                                                logger)

        # data class with electrical current samples
        self.electrical_analytics = ElectricalAnalytics()

        logger.info(f"server opc: {self.server_url}")


    def calculate_integr_analytics(self,
                                    el_current_ph1_samples,
                                    el_current_ph2_samples,
                                    el_current_ph3_samples,
                                    z_threshold_integr
                                    ):
        """Calculate definite integral of electrical current samples """

        el_current_integr_ph1_total = el_current_ph1_samples.sum()
        el_current_integr_ph2_total = el_current_ph2_samples.sum()
        el_current_integr_ph3_total = el_current_ph3_samples.sum()

        self.el_current_integr_ph1_analytics.z_score_thresh = z_threshold_integr
        self.el_current_integr_ph2_analytics.z_score_thresh = z_threshold_integr
        self.el_current_integr_ph3_analytics.z_score_thresh = z_threshold_integr

        self.el_current_integr_ph1_analytics.check_if_anomaly(el_current_integr_ph1_total)
        self.el_current_integr_ph2_analytics.check_if_anomaly(el_current_integr_ph2_total)
        self.el_current_integr_ph3_analytics.check_if_anomaly(el_current_integr_ph3_total)

        self.el_current_integr_ph1_analytics.calculate_anomaly_ratio()
        self.el_current_integr_ph2_analytics.calculate_anomaly_ratio()
        self.el_current_integr_ph3_analytics.calculate_anomaly_ratio()
        return el_current_integr_ph1_total, \
                el_current_integr_ph2_total, \
                el_current_integr_ph3_total


    def calculate_el_current_assymetry(self,
                                       el_current_integr_ph1_total,
                                       el_current_integr_ph2_total,
                                       el_current_integr_ph3_total):
        """
        Calculate electrical current assymetry

        Args:
            el_current_integr_ph1/2/3_total: total finite integral value from collected samples
        """

        el_current_integr_mean = (el_current_integr_ph1_total +
                        el_current_integr_ph2_total +
                        el_current_integr_ph3_total) / 3

        el_current_assymetry = 100 * ((
                                abs(el_current_integr_ph1_total - el_current_integr_mean) + \
                                abs(el_current_integr_ph2_total - el_current_integr_mean) + \
                                abs(el_current_integr_ph3_total - el_current_integr_mean)
        ) / el_current_integr_mean)

        return el_current_assymetry


    def calculate_inrush_current_analytics(self,
                                           el_current_ph1_samples,
                                           el_current_ph2_samples,
                                           el_current_ph3_samples,
                                           z_threshold_inrush,
                                           height_of_peak,
                                           peak_number):
        """
        Calculate inrush current in electrical current samples

        Args:
            el_current_ph1/2/3_samples: electrical current samples from phase L1/L2/L3
            height_of_peak: threshold for peak detection algorithm
            peak_number: which peak in a row should be taken into inrush current detection
        """

        # Find inrush current as first peak in electrical current curve
        el_current_peaks_ph1, _ = find_peaks(el_current_ph1_samples, height=height_of_peak)
        el_current_peaks_ph2, _ = find_peaks(el_current_ph2_samples, height=height_of_peak)
        el_current_peaks_ph3, _ = find_peaks(el_current_ph3_samples, height=height_of_peak)

        # Check if inrush current L1,L2,L3 is anomaly (first founded peak = inrush current)
        if len(el_current_peaks_ph1) > 0 and peak_number <= len(el_current_peaks_ph1):
            inrush_current_ph1 = el_current_ph1_samples[el_current_peaks_ph1[peak_number-1]]
            self.el_inrush_current_ph1_analytics.z_score_thresh = z_threshold_inrush
            self.el_inrush_current_ph1_analytics.check_if_anomaly(inrush_current_ph1)
            self.el_inrush_current_ph1_analytics.calculate_anomaly_ratio()

        if len(el_current_peaks_ph2) > 0 and peak_number <= len(el_current_peaks_ph2):
            inrush_current_ph2 = el_current_ph2_samples[el_current_peaks_ph2[peak_number-1]]
            self.el_inrush_current_ph2_analytics.z_score_thresh = z_threshold_inrush
            self.el_inrush_current_ph2_analytics.check_if_anomaly(inrush_current_ph2)
            self.el_inrush_current_ph2_analytics.calculate_anomaly_ratio()

        if len(el_current_peaks_ph3) > 0 and peak_number <= len(el_current_peaks_ph3):
            inrush_current_ph3 = el_current_ph3_samples[el_current_peaks_ph3[peak_number-1]]
            self.el_inrush_current_ph3_analytics.z_score_thresh = z_threshold_inrush
            self.el_inrush_current_ph3_analytics.check_if_anomaly(inrush_current_ph3)
            self.el_inrush_current_ph3_analytics.calculate_anomaly_ratio()

        try:
            return inrush_current_ph1, \
                    inrush_current_ph2, \
                    inrush_current_ph3
        except Exception as e:
            logger.error(f"*** Error: {e} - No inrush current detected ***")
            return False, False, False


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
                logger.info("Connected to OPC Server")
                break
            except Exception as e:
                logger.error(f"Unable to connect ot OPC server {e}")
                logger.error(
                    f"Trying to re-establish connection with OPC server in 3 seconds "
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
                logger.info(f"Configured node: {self.node}")
            else:
                logger.error("OPC client is not created!")
        else:
            logger.error("Invalid Node id")


    def read_values(self):
        """
        Read values from the OPC UA server and write them to InfluxDB.
        """

        try:
            # Hold the last time stamp of each sensor value (key:value pair)
            measurement_last_ts = {}
            while True:

                try:
                    # read opc ua struct from PLC
                    opc_node_children = self.node.get_children()

                    line_name     = opc_node_children[0].get_value()
                    machine_name  = opc_node_children[1].get_value()
                    device_name   = opc_node_children[2].get_value()
                    device_state   = opc_node_children[3].get_value()
                    synch_pulse   = opc_node_children[4].get_value()
                    timestamp     = opc_node_children[5].get_value()
                    el_current_phase1     = opc_node_children[6].get_children()[8].get_value()
                    el_current_phase2     = opc_node_children[6].get_children()[17].get_value()
                    el_current_phase3     = opc_node_children[6].get_children()[26].get_value()

                except Exception as e:
                    logger.error(f"Error reading node {self.node} || {opc_node_children}: {e}")
                    continue
                else:

                    # time stamp differs i.e. new data
                    if measurement_last_ts.get(str(device_name)) != timestamp:

                        if device_state == "Running":
                            # append data to array while device in 'Running' state
                            self.electrical_analytics.append_samples(el_current_phase1,
                                                                el_current_phase2,
                                                                el_current_phase3)

                        elif device_state != "Running" and synch_pulse is True:
                            # Reinitilize(clear) array with samples when
                            # not 'Running' and SynchPulse is true.
                            # Running state must be longer than SynchPulse
                            self.electrical_analytics.clear_samples()
                        elif (
                            # not 'Running' anymore and enough samples collected
                            # i.e. it can perform anomaly detection analytics
                            device_state != "Running"
                            and self.electrical_analytics.samples_number_ph1 > 0
                            and self.electrical_analytics.samples_number_ph2 > 0
                            and self.electrical_analytics.samples_number_ph3 > 0):

                            # Calculate definite integral of electrical current samples
                            # and check if it is anomaly
                            self.electrical_analytics.el_current_integr_ph1_total,\
                            self.electrical_analytics.el_current_integr_ph2_total,\
                            self.electrical_analytics.el_current_integr_ph3_total = \
                            self.calculate_integr_analytics(
                                        self.electrical_analytics.el_current_ph1_samples,
                                        self.electrical_analytics.el_current_ph2_samples,
                                        self.electrical_analytics.el_current_ph3_samples,
                                        Z_SCORE_THRESHOLD
                                        )

                            # Calculate electrical current assymetry
                            el_current_assymetry = self.calculate_el_current_assymetry(
                                                        self.electrical_analytics.el_current_integr_ph1_total,
                                                        self.electrical_analytics.el_current_integr_ph2_total,
                                                        self.electrical_analytics.el_current_integr_ph3_total,
                                                        )

                            # Calculate inrush current and check if it is anomaly
                            el_inrush_current_ph1, \
                            el_inrush_current_ph2, \
                            el_inrush_current_ph3, = \
                            self.calculate_inrush_current_analytics(
                                                        self.electrical_analytics.el_current_ph1_samples,
                                                        self.electrical_analytics.el_current_ph2_samples,
                                                        self.electrical_analytics.el_current_ph3_samples,
                                                        Z_SCORE_THRESHOLD,
                                                        CURRENT_PEAK_HEIGHT,
                                                        CURRENT_PEAK_NUMBER)


                            # Write analytics of sensor data to InfluxDB.
                            if el_inrush_current_ph1 is not False \
                                and el_inrush_current_ph2 is not False \
                                and el_inrush_current_ph3 is not False:
                                try:
                                    measurement = "ElectricalAnalytics"
                                    point = (
                                        influxdb_client.Point(measurement)
                                        .tag("line_name", str(line_name))
                                        .tag("machine_name", str(machine_name))
                                        .tag("device_name", device_name)
                                        .field("el_current_assymetry", round(float(el_current_assymetry), 2))
                                        .field("el_current_integral_ph1", round(float(self.electrical_analytics.el_current_integr_ph1_total), 4))
                                        .field("el_current_integral_ph2", round(float(self.electrical_analytics.el_current_integr_ph2_total), 4))
                                        .field("el_current_integral_ph3", round(float(self.electrical_analytics.el_current_integr_ph3_total), 4))
                                        .field("el_current_integral_ph1_z_score", round(float(self.el_current_integr_ph1_analytics.z_score), 4))
                                        .field("el_current_integral_ph1_z_score_thresh", round(float(self.el_current_integr_ph1_analytics .z_score_thresh), 4))
                                        .field("el_current_integral_ph2_z_score", round(float(self.el_current_integr_ph2_analytics.z_score), 4))
                                        .field("el_current_integral_ph2_z_score_thresh", round(float(self.el_current_integr_ph2_analytics.z_score_thresh), 4))
                                        .field("el_current_integral_ph3_z_score", round(float(self.el_current_integr_ph3_analytics .z_score), 4))
                                        .field("el_current_integral_ph3_z_score_thresh", round(float(self.el_current_integr_ph3_analytics.z_score_thresh), 4))

                                        .field("el_current_integral_ph1_anomaly", int(self.el_inrush_current_ph1_analytics.anomaly))
                                        .field("el_current_integral_ph2_anomaly", int(self.el_inrush_current_ph2_analytics.anomaly))
                                        .field("el_current_integral_ph3_anomaly", int(self.el_inrush_current_ph3_analytics.anomaly))
                                        .field("el_current_integral_ph1_anomaly_ratio", round(float(self.el_inrush_current_ph1_analytics.anomaly_ratio), 4))
                                        .field("el_current_integral_ph2_anomaly_ratio", round(float(self.el_inrush_current_ph2_analytics.anomaly_ratio), 4))
                                        .field("el_current_integral_ph3_anomaly_ratio", round(float(self.el_inrush_current_ph3_analytics.anomaly_ratio), 4))
                                        .field("el_inrush_current_ph1", round(float(el_inrush_current_ph1), 4))
                                        .field("el_inrush_current_ph2", round(float(el_inrush_current_ph2), 4))
                                        .field("el_inrush_current_ph3", round(float(el_inrush_current_ph3), 4))
                                        .field("el_inrush_current_ph1_anomaly", int(self.el_inrush_current_ph1_analytics.anomaly))
                                        .field("el_inrush_current_ph2_anomaly", int(self.el_inrush_current_ph1_analytics.anomaly))
                                        .field("el_inrush_current_ph3_anomaly", int(self.el_inrush_current_ph1_analytics.anomaly))
                                        .field("el_inrush_current_ph1_anomaly_ratio", round(float(self.el_inrush_current_ph1_analytics.anomaly_ratio), 4))
                                        .field("el_inrush_current_ph2_anomaly_ratio", round(float(self.el_inrush_current_ph1_analytics.anomaly_ratio), 4))
                                        .field("el_inrush_current_ph3_anomaly_ratio", round(float(self.el_inrush_current_ph1_analytics.anomaly_ratio), 4))

                                        .time(time=datetime.fromtimestamp(int(timestamp) / 1000, UTC),
                                            write_precision='ms')
                                            )

                                    with influx_client.write_api(write_options=write_options) as write_api:
                                        write_api.write(INFLUX_BUCKET_NAME, INFLUX_ORG, point)

                                except Exception as e:
                                    logger.error(f"Send data to InfluxDB failed. Error code/reason: {e}")

                            # Clear samples after data sent to InfluxDB
                            self.electrical_analytics.clear_samples()

                    else:
                        # timestamp same, no new data
                        pass

                    # store the last time stamp of each sensor value
                    measurement_last_ts.update({str(device_name):timestamp})

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
            measurement = "VibSensor"
            point = (
                influxdb_client.Point(measurement)
                .tag("line_name", str(sensor_data[1]))
                .tag("machine_name", str(sensor_data[2]))
                .tag("sensor_name", str(sensor_data[3]))
                .field("vib_accel_rms_x", float(round(sensor_data[4], 4)))
                .field("vib_accel_rms_y", float(round(sensor_data[5], 4)))
                .field("vib_accel_rms_z", float(round(sensor_data[6], 4)))
                .field("vib_accel_rms_total", float(round(sensor_data[7], 4)))
                .field("anomaly", int(sensor_data[8]))
                .field("anomaly_ratio", round(float(sensor_data[9]), 4))
                .field("model_avg", round(float(sensor_data[10]), 4))
                .field("z_score", round(float(sensor_data[11]), 4))
                .field("z_score_thresh", round(float(sensor_data[12]), 4))
                .time(time=datetime.fromtimestamp(int(sensor_data[13]) / 1000, UTC),
                    write_precision='ms')
            )

            with influx_client.write_api(write_options=write_options) as write_api:
                write_api.write(INFLUX_BUCKET_NAME, INFLUX_ORG, point)

        except Exception as e:
            logger.error(f"Send data to InfluxDB failed. Error code/reason: {e}")


# Main function of script
if __name__ == "__main__":

    # Configure connection to InfluxDB database
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
        logger.error(f"Configuring InfluxDB failed. Error code/reason: {e}")


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
