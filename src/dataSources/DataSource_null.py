"""
A null input
"""

import pprint as pp
from typing import Tuple
import logging
import time

import numpy as np

from dataSources import DataSource

logger = logging.getLogger('spectrum_logger')

module_type = "null"
help_string = f"{module_type}:xxx \t- xxx ignored parameter"
web_help_string = "xxx - ignored parameter"

import_error_msg = ""

# return an error string if we are not available
def is_available() -> Tuple[str, str]:
    return module_type, import_error_msg


class Input(DataSource.DataSource):

    def __init__(self,
                 source: str,
                 data_type: str,
                 sample_rate: float,
                 centre_frequency: float,
                 input_bw: float):
        """
        The null input source

        :param source: xxx, ignored
        :param data_type: Not used
        :param sample_rate: The sample rate we will set the source to
        :param centre_frequency: Not used
        :param sleep_time: Time in seconds between reads, not used on most sources
        :param input_bw: The filtering of the input, may not be configurable
        """
        super().__init__(source, data_type, sample_rate, centre_frequency, input_bw)

        self._connected = True
        super().set_help(help_string)
        super().set_web_help(web_help_string)

    def open(self) -> bool:
        self._error = "Null device"
        return False

    def read_cplx_samples(self, number_samples: int) -> Tuple[np.array, float]:
        """
            Always no samples
        """
        complex_data = None
        rx_time = 0
        time.sleep(1.0)
        return complex_data, rx_time
