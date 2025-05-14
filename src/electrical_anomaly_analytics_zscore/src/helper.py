"""
Helper for script.py
It inculdes :
-'get_env_var' for reading environmental variables

- class 'ElectricalAnalytics' which stores real-time samples
of electrical current and calculated definite integral

- class 'AnomalyDetectionZscore' which calculates anomalies
in integral of electrical current samples over fixed time period
and in electrical inrush current value in fixed time period
"""

import os
import statistics
import logging
import numpy as np

helper_logger = logging.getLogger(__name__)

def get_env_var(
    env_var: str, req_type=None, default: str | int | float = None
) -> str | int | float:
    """Read env variables and return its value with log information

    Args:
        env_var (str): Name of enviromental variable
        req_type (str, int, float): define which type shoud have returned env_var variable.
        default (str, int, float): will be returnet if is set and env variable does not exist

    Raises:
        SystemExit: Stop program if set type_var has not passed validate
        SystemExit: Stop program if env does not exist and default is not set
        SystemExit: Stop program if cannot convert env variable to req_type
    """
    # set local variable. Type and value of read env variable
    env_type = type(env_var)
    env_val = os.getenv(env_var, None)

    # check if input convert type is correct or is None (if not, return error and stop program)
    allow_convert = [str, int, float]
    if req_type not in allow_convert and req_type is not None:
        helper_logger.error(
            f"Cannot convert value of env {env_var} to {req_type}. \
                Allowed conversion type: str, int, float"
        )
        raise SystemExit

    # Return value of env variable
    if env_val is None and default is None:
        # env does not exist and we did not set default value
        helper_logger.error(f"Env variable {env_var} does not exist")
        raise SystemExit
    elif env_val is None:
        # env does not exist but return default (default is different than none)
        helper_logger.warning(
            f"Env variable {env_var} does not exist, return default value: {default}"
        )
        return default
    elif env_type is not req_type and req_type is not None:
        # env var exist and it's type is diffrent than what we set
        try:
            converted_env = req_type(env_val)
            helper_logger.info(
                f"Env variable {env_var} value: {env_val}. Converted from {env_type} to {req_type}."
            )
            return converted_env
        except Exception as e:
            helper_logger.error(
                f"Convert env_var variable {env_var} from {env_type} to {req_type} failed: {e}"
            )
            raise SystemExit
    else:
        # env exist, is the same type (or we not set type) so we return it
        helper_logger.info(f"Env variable {env_var} value: {env_val}, type: {env_type}")
        return env_val


class ElectricalAnalytics:
    """ Class to store electrical current samples and calculate definite integral"""

    def __init__(self ) -> None:
        # array where electrical current samples are stored
        self.el_current_ph1_samples = np.array([])
        self.el_current_ph2_samples = np.array([])
        self.el_current_ph3_samples = np.array([])

        # calculated definite integral of electrical current samples
        self.el_current_integr_ph1_total = 0
        self.el_current_integr_ph2_total = 0
        self.el_current_integr_ph3_total = 0

    def append_samples(self, phase1, phase2, phase3):
        """Append new samples to array of electrical current samples"""
        self.el_current_ph1_samples = np.append(self.el_current_ph1_samples, phase1)
        self.el_current_ph2_samples = np.append(self.el_current_ph2_samples, phase2)
        self.el_current_ph3_samples = np.append(self.el_current_ph3_samples, phase3)

    def clear_samples(self):
        """Clear array of electrical current samples"""
        self.el_current_ph1_samples = np.array([])
        self.el_current_ph2_samples = np.array([])
        self.el_current_ph3_samples = np.array([])

    @property
    def samples_number_ph1(self) -> int:
        """Return number of samples in array"""
        return len(self.el_current_ph1_samples)

    @property
    def samples_number_ph2(self) -> int:
        """Return number of samples in array"""
        return len(self.el_current_ph2_samples)

    @property
    def samples_number_ph3(self) -> int:
        """Return number of samples in array"""
        return len(self.el_current_ph3_samples)


class AnomalyDetectionZscore:
    """
        Analyse real-time data from electrical device
        and apply z-score algorithm to detect anomalies
        in following electrical data:
        - integral of electrical current samples over
            fixed time period
        - electrical inrush current value in fixed
            time period 

        model_data          list where real-time (non anomalous) data are stored
        model_size          definition how many data points should be in `model_data`
        anomaly_list        list with anomaly detection results (1 and 0)
        anomaly_ratio       percentage of anomalous data in `anomaly_list`
        anomaly             result if current data point is anomaly (1) or not (0)
        model_avg           avarage mean of `model_data`
        model_std_dev       standard deviation of `model_data`
        z_score             calculated z-score value for single sensor data
        z_score_thresh      threshold above which sensor data is interpeted as anomalous
        name                name of the object/sensor on which the algorithm is applied
    """


    def __init__(self, name: str, model_size: int, anomaly_list_size: int, logger) -> None:
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
        self.logger = logger

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

    # setter for z-score threshold value
    @z_score_thresh.setter
    def z_score_thresh(self, z_score_threshold: float):
        if z_score_threshold == 0:
            self.logger.error("Z-score threshold must be above zero")
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
        """
        Sum all anomalies results (0 and 1) from `anomaly_list`
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
            self.logger.error(
                f"Calculation `anomaly ratio of model` {self._name} failed. Error code/reason: {e}"
            )

    def check_if_anomaly(self, value: float):
        """Z-score algorithm to check if argument value is anomaly or not.

        Args:
            value (any): input value (sensor data) to be evaluated by algorithm
        """

        try:
            if self.is_model_complete():
                # recalculate the avg and std dev using only data points which are not anomaly
                self._model_avg = abs(statistics.mean(self._model_data))
                self._model_std_dev = abs(statistics.stdev(self._model_data))
                # avoid division by zero
                if self._model_std_dev == 0:
                    self._model_std_dev = 0.001
                
                self._z_score = round((abs(value) - self._model_avg) / self._model_std_dev, 4)

                # Check if new point is beyond z-score threshold i.e. this is anomaly
                if abs(self._z_score) > self._z_score_thresh:
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
            self.logger.error(
                f'Calculation `anomaly of model` "{self._name}" failed. Error code/reason: {e}'
            )


