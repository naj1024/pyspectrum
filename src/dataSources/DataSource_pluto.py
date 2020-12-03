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
web_help_string = "IP address - The Ip or resolvable name of the Pluto device, e.g. 192.168.2.1"

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
                 centre_frequency: float,
                 input_bw: float):
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
        :param input_bw: The filtering of the input, may not be configurable
        """
        # Driver converts to floating point for us, underlying data from ad936x was 16bit i/q
        self._constant_data_type = "16tle"
        super().__init__(ip_address, number_complex_samples, self._constant_data_type, sample_rate,
                         centre_frequency, input_bw)
        self._sdr = None
        self._connected = False
        self._gain_modes = ["manual", "fast_attack", "slow_attack", "hybrid"]  # would ask, but can't
        super().set_gain_mode(self._gain_modes[0])
        super().set_help(help_string)
        super().set_web_help(web_help_string)

    def open(self) -> bool:
        global import_error_msg
        if import_error_msg != "":
            msgs = f"no {module_type} device available, {import_error_msg}"
            self._error = msgs
            logger.error(msgs)
            raise ValueError(msgs)

        # Create device from specific uri address
        try:
            self._sdr = adi.Pluto(uri="ip:" + self._source)  # use adi.Pluto() for USB
        except Exception:
            msgs = f"failed to connect to {self._source}"
            self._error = str(msgs)
            logger.error(msgs)
            raise ValueError(msgs)

        logger.debug(f"Connected to {module_type} on {self._source}")

        # pluto is not consistent in its errors so check ranges here
        if self._centre_frequency < 70e6 or self._centre_frequency > 6e9:
            msgs = "centre frequency must be between 70MHz and 6GHz, "
            msgs += f"attempted {self._centre_frequency / 1e6:0.6}MHz, "
            self._centre_frequency = 100.0e6
            msgs += f"set {self._centre_frequency / 1e6:0.6}MHz. \n"
            self._error = msgs
            logger.error(msgs)

        # pluto does raise errors for sample rate though, but we check so we don't raise errors
        if self._sample_rate < 521e3 or self._sample_rate > 61e6:
            msgs = "sample rate must be between 521kH and 61MHz, "
            msgs += f"attempted {self._sample_rate / 1e6:0.6}MHz, "
            self._sample_rate = 1.0e6
            msgs += f"set {self._sample_rate / 1e6:0.6}MHz. "
            self._error += msgs

        try:
            self._sdr.rx_buffer_size = self._number_complex_samples  # sets how many complex samples we get each rx()
            self._sdr.sample_rate = self._sample_rate
            self._sdr.rx_lo = int(self._centre_frequency)
            self._sdr.rx_rf_bandwidth = int(self._sdr_filter_bandwidth)
            # AGC mode will depend on environment, lots of bursting signals or lots of continuous signals
            self.set_gain_mode(self._gain_mode)  # self._sdr.gain_control_mode_chan0 = self._gain_mode
            self.set_gain(40)
        except Exception as err:
            msgs = f"problem with initialisation {err}"
            self._error += f"str(msgs),\n"
            logger.error(msgs)
            raise ValueError(msgs)

        if self._number_complex_samples < 1024:
            msgs = f"sis best with sizes above 1024"
            logger.warning(msgs)

        logger.debug(f"{module_type}: {self._centre_frequency / 1e6:.6}MHz @ {self._sample_rate / 1e6:.3f}Msps")
        self._connected = True
        return self._connected

    def get_sample_rate(self) -> float:
        if self._sdr:
            self._sample_rate = self._sdr.sample_rate
            return self._sample_rate

    def get_centre_frequency(self) -> float:
        if self._sdr:
            self._centre_frequency = float(self._sdr.rx_lo)
            return self._centre_frequency

    def set_sample_rate(self, sr: float) -> None:
        if self._sdr:
            if sr >= 521e3 and sr <= 61e6:
                self._sdr.sample_rate = sr
                self._sample_rate = self._sdr.sample_rate
                self._sdr.rx_rf_bandwidth = int(sr)  # TODO: make this separate

    def set_centre_frequency(self, cf: float) -> None:
        if self._sdr:
            if (cf >= 70.0e6) and (cf <= 6.0e9):
                self._sdr.rx_lo = int(cf)
                self._centre_frequency = float(self._sdr.rx_lo)
                # logger.error(f"cf set to {self._centre_frequency} from {cf} {int(cf)}")

    def set_sample_type(self, data_type: str) -> None:
        # we can't set a different sample type on this source
        super().set_sample_type(self._constant_data_type)

    def get_gain(self) -> float:
        if self._sdr:
            self._gain = self._sdr.rx_hardwaregain_chan0
        return self._gain

    def set_gain(self, gain: float) -> None:
        self._gain = float(gain)
        if self._gain > 73:
            self._gain = 73
        if self._gain < 0:
            self._gain = 0
        if self._sdr:
            self._sdr.rx_hardwaregain_chan0 = self._gain

    def get_gain_mode(self) -> str:
        if self._sdr:
            self._gain_mode = self._sdr.gain_control_mode_chan0
        return self._gain_mode

    def set_gain_mode(self, mode: str) -> None:
        if mode in self._gain_modes:
            self._gain_mode = mode
            if self._sdr:
                self._sdr.gain_control_mode_chan0 = self._gain_mode

    def set_sdr_filter_bandwidth(self, bw: float) -> None:
        if self._sdr:
            self._sdr.rx_rf_bandwidth = int(bw)
            self._sdr_filter_bandwidth = self._sdr.rx_rf_bandwidth

    def get_sdr_filter_bandwidth(self) -> float:
        if self._sdr:
            self._sdr_filter_bandwidth = self._sdr.rx_rf_bandwidth
        return self._sdr_filter_bandwidth

    def read_cplx_samples(self) -> Tuple[np.array, float]:
        """
        Get complex float samples from the device

        Note that we don't use unpack() for this device

        :return: A tuple of a numpy array of complex samples and time in nsec
        """
        complex_data = None
        rx_time = 0

        if self._connected and self._sdr:
            try:
                complex_data = self._sdr.rx()  # the samples here are complex128 i.e. full doubles
                rx_time = self.get_time_ns()
                complex_data = complex_data / 4096.0  # 12bit
                complex_data = np.array(complex_data, dtype=np.complex64)  # if we need all values to be 32bit floats
            except Exception  as err:
                self._connected = False
                self._error = str(err)
                logger.error(self._error)
                raise ValueError(err)

        return complex_data, rx_time
