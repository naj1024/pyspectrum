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
help_string = f"{module_type}:Number \t- The device number to use, normally 0"
web_help_string = "Number - The device number to use, normally 0"

# The following must match the rtl_sdr C source code definitions in rtl_sdr.h for enum rtlsdr_tuner{}
allowed_tuner_types = {0: "Unknown",
                       1: "E4000",
                       2: "FC0012",
                       3: "FC0013",
                       4: "FC2580",
                       5: "R820T",
                       6: "R828D"}


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
                 centre_frequency: float,
                 input_bw: float):
        """
        The rtlsdr input source

        :param source: The device number, normally zero
        :param number_complex_samples: The number of complex samples we require each request
        :param data_type: The data type the rtlsdr is providing, we will convert this
        :param sample_rate: The sample rate we will set the source to, note true sps is set from the device
        :param centre_frequency: The centre frequency the source will be set to
        :param input_bw: The filtering of the input, may not be configurable
        """
        # Driver converts to floating point for us, underlying is 8o?
        self._constant_data_type = "16tle"
        super().__init__(source, number_complex_samples, self._constant_data_type, sample_rate,
                         centre_frequency, input_bw)
        self._connected = False
        self._sdr = None
        self._tuner_type = 0
        self._device_index = 0
        self._gain_modes = ["auto", "manual"]  # would ask, but can't
        super().set_gain_mode(self._gain_modes[0])
        super().set_help(help_string)
        super().set_web_help(web_help_string)

    def open(self) -> bool:
        global import_error_msg
        if import_error_msg != "":
            msgs = f"No {module_type} support available, ", import_error_msg
            self._error = msgs
            logger.error(msgs)
            raise ValueError(msgs)

        try:
            self._device_index = int(self._source)
        except ValueError as err:
            msgs = f"port number from {self._source}, {err}"
            self._error = str(err)
            logger.error(msgs)
            raise ValueError(err)

        try:
            self._sdr = RtlSdr(device_index=self._device_index)
        except Exception as err:
            self._error = f"Failed to connect {str(err)}"
            logger.error(self._error)
            raise ValueError(self._error)

        self._tuner_type = self._sdr.get_tuner_type()

        logger.debug(f"Connected to {module_type}")

        try:
            self.set_sample_rate(self._sample_rate)
            self.set_centre_frequency(self._centre_frequency)
            # self._sdr.freq_correction = 0 # ppm
            self.set_gain_mode('auto')
            self.set_gain(0)
        except ValueError:
            pass
        except Exception as err:
            self._error = str(err)
            raise ValueError(err)

        # recover the true values from the device
        self._sample_rate = float(self._sdr.get_sample_rate())
        self._centre_frequency = float(self._sdr.get_center_freq())
        logger.debug(f"{allowed_tuner_types[self._tuner_type]} {self._centre_frequency / 1e6:.6}MHz @ "
                     f"{self._sample_rate:.3f}sps")
        self._connected = True

        return self._connected

    def close(self) -> None:
        if self._sdr:
            self._sdr.close()
            self._sdr = None
        self._connected = False

    def get_sample_rate(self) -> float:
        if self._sdr:
            self._sample_rate = float(self._sdr.get_sample_rate())
        return self._sample_rate

    def get_centre_frequency(self) -> float:
        if self._sdr:
            self._centre_frequency = float(self._sdr.get_center_freq())
        return self._centre_frequency

    def set_sample_type(self, data_type: str) -> None:
        # we can't set a different sample type on this source
        super().set_sample_type(self._constant_data_type)

    def set_sample_rate(self, sample_rate: float) -> None:
        # rtlsdr has limits on allowed sample rates
        # from librtlsdr.c data_source.get_bytes_per_sample()
        # 	/* check if the rate is supported by the resampler */
        # 	if ((samp_rate <= 225000) || (samp_rate > 3200000) ||
        # 	   ((samp_rate > 300000) && (samp_rate <= 900000))) {
        # 		fprintf(stderr, "Invalid sample rate: %u Hz\n", samp_rate);
        # 		return -EINVAL;
        # 	}
        # logger.info(f"set sr rtlsdr tuner type {self._tuner_type}, {allowed_tuner_types[self._tuner_type]}")

        if (sample_rate <= 225000) or (sample_rate > 3200000) or ((sample_rate > 300000) and (sample_rate <= 900000)):
            err = f"{module_type} invalid sample rate, {sample_rate}sps, 225000-3000000 and not 300000-900000"
            self._error = err
            logger.error(err)
            sample_rate = 1e6  # something safe

        self._sample_rate = sample_rate
        if self._sdr:
            try:
                self._sdr.sample_rate = sample_rate
                self._sample_rate = float(self._sdr.get_sample_rate())
            except Exception as err:
                self._error = str(err)
                logger.debug(f"bad sr {sample_rate} now {self._sample_rate}")
                raise ValueError(err)

        logger.info(f"Set sample rate {sample_rate}sps")

    def set_centre_frequency(self, frequency: float) -> None:
        # limits depend on tuner type: from https://wiki.radioreference.com/index.php/RTL-SDR
        # Tuner 	             Frequency Range
        # =======================================
        # Elonics E4000 	     52 – 1100 MHz / 1250 - 2200 MHz
        # Rafael Micro R820T(2)  24 – 1766 MHz
        # Fitipower FC0013 	     22 – 1100 MHz
        # Fitipower FC0012 	     22 - 948.6 MHz
        # FCI FC2580 	         146 – 308 MHz / 438 – 924 MHz

        freq_ok = True
        # logger.info(f"set cf rtlsdr tuner type {self._tuner_type}, {allowed_tuner_types[self._tuner_type]}")

        # what type of tuner do we have ?
        freq_range = ""
        if self._tuner_type == 1:
            # E4000
            if (frequency < 52e6) or (frequency > 2200e6):
                freq_ok = False
                freq_range = "52 – 1100 MHz and 1250 - 2200 MHz"
            elif (frequency > 1100e6) and (frequency < 1250e6):
                freq_ok = False
                freq_range = "52 – 1100 MHz and 1250 - 2200 MHz"
        elif self._tuner_type == 2:
            # FC0012
            if (frequency < 22e6) or (frequency > 948.6e6):
                freq_ok = False
                freq_range = "22 - 948.6 MHz"
        elif self._tuner_type == 3:
            # FC0013
            if (frequency < 22e6) or (frequency > 1100e6):
                freq_ok = False
                freq_range = "22 – 1100 MHz"
        elif self._tuner_type == 4:
            # FC2580
            if (frequency < 146e6) or (frequency > 924e6):
                freq_ok = False
                freq_range = "146 – 308 MHz and 438 – 924 MHz"
            elif (frequency > 308e6) and (frequency < 438e6):
                freq_ok = False
                freq_range = "146 – 308 MHz and 438 – 924 MHz"
        elif self._tuner_type == 5 or self._tuner_type == 6:
            # R820T or R828D
            if (frequency < 24e6) or (frequency > 1.766e9):
                freq_ok = False
                freq_range = "24 – 1766 MHz"
        else:
            self._error = f"Unknown tuner type {self._tuner_type}, frequency range checking impossible"
            logger.error(self._error)
            raise ValueError(self._error)

        if not freq_ok:
            self._error = f"{allowed_tuner_types[self._tuner_type]} invalid frequency {frequency}Hz, " \
                          f"outside range {freq_range}"
            frequency = 600e6  # something safe
            logger.error(self._error)

        if self._sdr:
            try:
                self._sdr.center_freq = frequency
                self._centre_frequency = float(self._sdr.get_center_freq())
                logger.info(f"Set frequency {frequency / 1e6:0.6f}MHz")
            except Exception as err:
                self._error = str(err)
                raise ValueError(err)

    def get_gain(self) -> float:
        if self._sdr:
            self._gain = self._sdr.get_gain()
        return self._gain

    def set_gain(self, gain: float) -> None:
        self._gain = gain
        if self._sdr:
            try:
                # horrible _sdr.set_gain() - either a number or string
                if self._gain_mode == 'auto':
                    self._sdr.set_gain('auto')
                else:
                    self._sdr.set_gain(float(gain))
            except Exception as err:
                self._error = f"failed to set gain of '{gain}'"
                raise ValueError(err)

    def set_gain_mode(self, mode: str) -> None:
        if mode in self._gain_modes:
            self._gain_mode = mode
            if self._sdr:
                # because the 'best' way to set the mode is to set the gain, apparently
                self.set_gain(self._gain)
        return

    def set_sdr_filter_bandwidth(self, bw: float) -> None:
        if self._sdr:
            try:
                self._sdr.set_bandwidth(int(bw))
            except Exception as msg:
                self._error += str(msg)
            self._sdr_filter_bandwidth = self._sdr.get_bandwidth()

    def get_sdr_filter_bandwidth(self) -> float:
        if self._sdr:
            self._sdr_filter_bandwidth = self._sdr.get_bandwidth()
        return self._sdr_filter_bandwidth

    def read_cplx_samples(self) -> Tuple[np.array, float]:
        """
        Get complex float samples from the device

        Note that we don't use unpack() for this device

        :return: A tuple of a numpy array of complex samples and time in nsec
        """
        complex_data = None
        rx_time = 0

        if self._sdr and self._connected:
            try:
                complex_data = self._sdr.read_samples(self._number_complex_samples)  # will return np.complex128
                rx_time = self.get_time_ns()
                complex_data = np.array(complex_data, dtype=np.complex64)  # (?) we need all values to be 32bit floats
            except Exception as err:
                self._connected = False
                self._error = str(err)
                logger.error(self._error)
                raise ValueError(err)

        return complex_data, rx_time
