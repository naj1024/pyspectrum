"""
RTLSDR class wrapper

Used with USB IP input
Requires librtlsdr to be installed, tested on Linux only
Requires pyrtlsdr to be installed - provides RtlSdr
"""

import numpy as np
from typing import Tuple
import logging
import time

from dataSources import DataSource

logger = logging.getLogger('spectrum_logger')

module_type = "rtlsdr"
help_string = f"{module_type}:Name \t- Name is anything, e.g. {module_type}:abc"

try:
    import_error_msg = ""
    from rtlsdr import RtlSdr
except ImportError as msg:
    RtlSdr = None
    import_error_msg = f"{module_type} source has an issue, " + str(msg)
    logger.info(import_error_msg)


# return an error string if we are not available
def is_available() -> Tuple[str, str]:
    return module_type, import_error_msg


class Input(DataSource.DataSource):

    def __init__(self,
                 source: str,
                 number_complex_samples: int,
                 data_type: str,
                 sample_rate: float,
                 centre_frequency: float):
        """
        The rtlsdr input source

        :param source: Not used
        :param number_complex_samples: The number of complex samples we require each request
        :param data_type: The data type the rtlsdr is providing, we will convert this
        :param sample_rate: The sample rate we will set the source to, note true sps is set from the device
        :param centre_frequency: The centre frequency the source will be set to
        """
        super().__init__(source, number_complex_samples, data_type, sample_rate, centre_frequency)

        global import_error_msg
        if import_error_msg != "":
            msgs = f"{module_type} No {module_type} support available, ", import_error_msg
            logger.error(msgs)
            raise ValueError(msgs)

        try:
            self._sdr = RtlSdr()
        except Exception:
            raise ValueError(f"{module_type} Failed to connect")

        logger.debug(f"Connected to {module_type}")

        try:
            self._sdr.sample_rate = self._sample_rate
            self._sdr.center_freq = self._centre_frequency
            # self._sdr.freq_correction = 0 # ppm
            self._sdr.gain = 'auto'
        except Exception as err_msg:
            msgs = f"{module_type} error: {err_msg}"
            logger.error(msgs)
            raise ValueError(msgs) from None

        # recover the true values from the device
        self._sample_rate = float(self._sdr.get_sample_rate())
        self._centre_frequency = float(self._sdr.get_center_freq())
        logger.debug(f"{module_type}: {self._centre_frequency / 1e6:.6}MHz @ {self._sample_rate:.3f}sps")
        self._connected = True

    def close(self) -> None:
        if self._sdr:
            self._sdr.close()

    def read_cplx_samples(self) -> Tuple[np.array, float]:
        """
        Get complex float samples from the device
        :return: A tuple of a numpy array of complex samples and time in nsec
        """
        complex_data = self._sdr.read_samples(self._number_complex_samples)  # will return np.complex128
        rx_time = time.time_ns()
        complex_data = np.array(complex_data, dtype=np.complex64)  # (?) we need all values to be 32bit floats
        return complex_data, rx_time
