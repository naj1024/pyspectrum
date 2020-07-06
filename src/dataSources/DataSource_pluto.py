"""
Pluto class wrapper

May have to use export PYTHONPATH=/usr/lib/python3.8/site-packages

NOTE that the pluto device will accept 70Mhz to 6GHz frequency and 60MHz sampling with the patch.
    but -
          anything above around 2Msps is going to drop samples silently
"""

import numpy as np
from typing import Tuple
import logging
import time

from dataSources import DataSource

logger = logging.getLogger('spectrum_logger')

module_type = "pluto"
help_string = f"{module_type}:IP\t- The Ip or resolvable name of the Pluto device, " \
              f"e.g. {module_type}:192.168.2.1"

try:
    import_error_msg = ""
    import adi  # analog devices device specifics for using iio
except ImportError as msg:
    adi = None
    import_error_msg = f"{module_type} source has issue, " + str(msg)
    logger.info(import_error_msg)


# return an error string if we are not available
def is_available() -> Tuple[str, str]:
    return module_type, import_error_msg


class Input(DataSource.DataSource):

    def __init__(self,
                 ip_address: str,
                 number_complex_samples: int,
                 data_type: str,
                 sample_rate: float,
                 centre_frequency: float):
        """
        The pluto device on a socket, not the USB connection

        The Pluto device will silently drop samples while maintaining a socket connection.

        If the software modification has been done to make it look like an ad9361 not the ad9363 on the board
        then you may find that random signals will appear below 300MHz.

        :param ip_address: The address the device should be on
        :param number_complex_samples: The number of complex samples we will get each time
        :param data_type: Not used
        :param sample_rate: The sample rate the pluto device will be set to, AND it's BW
        :param centre_frequency: The Centre frequency we will tune to
        """
        super().__init__(ip_address, number_complex_samples, data_type, sample_rate, centre_frequency)

        global import_error_msg
        if import_error_msg != "":
            msgs = f"{module_type} No {module_type} device available, {import_error_msg}"
            logger.error(msgs)
            raise ValueError(msgs)

        # Create device from specific uri address
        try:
            self._sdr = adi.Pluto(uri="ip:" + self._source)  # use adi.Pluto() for USB
        except Exception:
            msgs = f"{module_type} Failed to connect"
            logger.error(msgs)
            raise ValueError(msgs)

        logger.debug(f"Connected to {module_type} on {self._source}")

        # pluto is not consistent in its errors so check ranges here
        if self._centre_frequency < 70e6 or self._centre_frequency > 6e9:
            msgs = f"{module_type} centre frequency must be between 70MHz and 6GHz, "
            msgs += f"attempted {self._centre_frequency / 1e6:0.6}MHz)"
            logger.error(msgs)
            raise ValueError(msgs)

        # pluto does raise errors for sample rate though, so commented this bit out
        # if self._sample_rate < 521e3 or self._sample_rate > 61e6:
        #     raise ValueError("Error: Pluto sample rate must be between 521ksps and 61Msps, "
        #                      f", attempted {self._sample_rate / 1e6:0.6}sps)")

        try:
            self._sdr.rx_buffer_size = self._number_complex_samples  # sets how many complex samples we get each rx()
            self._sdr.sample_rate = self._sample_rate
            self._sdr.rx_lo = int(self._centre_frequency)
            self._sdr.rx_rf_bandwidth = int(self._sample_rate)
            # AGC mode will depend on environment, lots of bursting signals or lots of continuous signals
            self._sdr.gain_control_mode_chan0 = "slow_attack"
        except Exception as err:
            msgs = f"{module_type} {err}"
            logger.error(msgs)
            raise ValueError(msgs)

        if self._number_complex_samples < 1024:
            msgs = f"{module_type} is best with sizes above 1024"
            logger.warning(msgs)

        logger.debug(f"{module_type}: {self._centre_frequency / 1e6:.6}MHz @ {self._sample_rate / 1e6:.3f}Msps")
        self._connected = True

    def read_cplx_samples(self) -> Tuple[np.array, float]:
        """
        Get complex float samples from the device
        :return: A tuple of a numpy array of complex samples and time in nsec
        """
        complex_data = self._sdr.rx()  # the samples here are complex128 i.e. full doubles
        rx_time = time.time_ns()
        complex_data = complex_data / 4096.0  # 12bit
        complex_data = np.array(complex_data, dtype=np.complex64)  # if we need all values to be 32bit floats
        return complex_data, rx_time
