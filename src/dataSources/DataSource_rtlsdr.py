"""
RTLSDR class wrapper

Used with USB IP input
Requires librtlsdr to be installed, tested on Linux only
Requires pyrtlsdr to be installed - provides RtlSdr

Under Linux
    You may need to blacklist the use of dvb which will claim the rtlsdr
    create no-dvb.conf in /etc/modprobe.d with contents:

        blacklist dvb_usb_rtl28xxu
        blacklist rtl2832
        blacklist rtl2830
"""

import logging
from typing import Tuple

import numpy as np

from dataSources import DataSource

logger = logging.getLogger('spectrum_logger')

module_type = "rtlsdr"
help_string = f"{module_type}:Number \t- The device number to use, normally 0. Use '?' for list"
web_help_string = "Number - The device number to use, normally 0. Use '?' for list"

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
    # is the import likely to find its underlying library
    from platform import system as _system
    from ctypes.util import find_library
    from os import environ

    lib = "rtlsdr"
    found = None
    # Windows is a mess for rtl libraries, can be librtlsdr.dll or rtlsdr.dll
    # rtlsdr for python expects rtlsdr.dll, for now - may change
    # where it is located is a mystery, put in on your path in environment variables
    if "Windows" in _system():
        lib = "rtlsdr.dll"
    found = find_library(lib)
    if not found and "Windows" in _system():
        # maybe it is librtlsdr.dll in windows
        lib = "librtlsdr.dll"
        found = find_library(lib)
        if found:
            mm = f"found {lib}, but this is not what the rtlsdr module requires, it expects rtlsdr.dll"
            logger.error(mm)
        mm = f"rtlsdr.dll search path was: {environ['PATH']}"
        logger.error(mm)
    if found:
        from rtlsdr import RtlSdr
    else:
        mm = f"rtlsdr library search path was: {environ['PATH']}"
        logger.error(mm)
        mm = f"Can't find library {lib}"
        raise ValueError(mm)

except (ImportError, ValueError) as msg:
    RtlSdr = None
    import_error_msg = f"{module_type} source has an issue: " + str(msg)
    logger.error(import_error_msg)


# return an error string if we are not available
def is_available() -> Tuple[str, str]:
    return module_type, import_error_msg


class Input(DataSource.DataSource):

    def __init__(self,
                 parameters: str,
                 data_type: str,
                 sample_rate: float,
                 centre_frequency: float,
                 input_bw: float):
        """
        The rtlsdr input source

        :param parameters: The device number, normally zero
        :param data_type: The data type the rtlsdr is providing, we will convert this
        :param sample_rate: The sample rate we will set the source to, note true sps is set from the device
        :param centre_frequency: The centre frequency the source will be set to
        :param input_bw: The filtering of the input, may not be configurable
        """
        # Driver converts to floating point for us, underlying is 8o?
        self._constant_data_type = "16tle"
        if not parameters or parameters == "":
            parameters = "0"  # default
        super().__init__(parameters, self._constant_data_type, sample_rate, centre_frequency, input_bw)
        self._name = module_type
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

        if self._parameters == "?":
            self._error = self.find_devices()
            return False

        try:
            self._device_index = int(self._parameters)
        except ValueError as err:
            msgs = f"port number from {self._parameters}, {err}"
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
            self.set_sample_rate_sps(self._sample_rate_sps)
            self.set_centre_frequency_hz(self._centre_frequency_hz)
            # self._sdr.freq_correction = 0 # ppm
            self.set_gain_mode('auto')
            self.set_gain(0)
        except ValueError:
            pass
        except Exception as err:
            self._error = str(err)
            raise ValueError(err)

        # recover the true values from the device
        self._sample_rate_sps = float(self._sdr.get_sample_rate())
        self._centre_frequency_hz = float(self._sdr.get_center_freq())
        logger.debug(f"{allowed_tuner_types[self._tuner_type]} {self._centre_frequency_hz / 1e6:.6}MHz @ "
                     f"{self._sample_rate_sps:.3f}sps")
        self._connected = True

        return self._connected

    def close(self) -> None:
        if self._sdr:
            self._sdr.close()
            self._sdr = None
        self._connected = False

    @staticmethod
    def find_devices() -> str:
        devices = ""
        # could do with a call that returns the valid device_index's
        max_device = 10
        for device in range(max_device):
            try:
                sdr = RtlSdr(device_index=device)
                type_of_tuner = sdr.get_tuner_type()
                # index = sdr.get_device_index_by_serial('0000001')  # permissions required
                # addresses = sdr.get_device_serial_addresses() # permissions required
                sdr.close()
                devices += f"device {device}, type {type_of_tuner} {allowed_tuner_types[type_of_tuner]}\n"
            except Exception:
                pass
        if devices == "":
            devices = f"No rtlsdr devices found, scanned 0 to {max_device - 1}"
        print(devices)
        return devices

    def get_sample_rate_sps(self) -> float:
        if self._sdr:
            self._sample_rate_sps = float(self._sdr.get_sample_rate())
        return self._sample_rate_sps

    def get_centre_frequency_hz(self) -> float:
        if self._sdr:
            if self._hw_ppm_compensation:
                self._centre_frequency_hz = float(self._sdr.get_center_freq())
        return self._centre_frequency_hz

    def set_sample_type(self, data_type: str) -> None:
        # we can't set a different sample type on this source
        super().set_sample_type(self._constant_data_type)

    def set_sample_rate_sps(self, sample_rate: float) -> None:
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

        self._rx_time = 0
        self._sample_rate_sps = sample_rate
        if self._sdr:
            try:
                self._sdr.sample_rate = sample_rate
                self._sample_rate_sps = float(self._sdr.get_sample_rate())
            except Exception as err:
                self._error = str(err)
                logger.debug(f"bad sr {sample_rate} now {self._sample_rate_sps}")

        logger.info(f"Set sample rate {sample_rate}sps")

    def set_centre_frequency_hz(self, frequency: float) -> None:
        # limits depend on tuner type: from https://wiki.radioreference.com/index.php/RTL-SDR
        # Tuner 	             Frequency Range
        # =======================================
        # Elonics E4000 	     52 – 1100 MHz / 1250 - 2200 MHz
        # Rafael Micro R820T(2)  24 – 1766 MHz
        # Fitipower FC0013 	     22 – 1100 MHz
        # Fitipower FC0012 	     22 - 948.6 MHz
        # FCI FC2580 	         146 – 308 MHz / 438 – 924 MHz

        freq_ok = True
        ok = True
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
            ok = False

        if not freq_ok:
            self._error = f"{allowed_tuner_types[self._tuner_type]} invalid frequency {frequency}Hz, " \
                          f"outside range {freq_range}"
            logger.error(self._error)
            ok = False

        if self._sdr and ok:
            try:
                if self._hw_ppm_compensation:
                    self._sdr.center_freq = frequency
                    self._centre_frequency_hz = float(self._sdr.get_center_freq())
                else:
                    self._centre_frequency_hz = frequency
                    self._sdr.center_freq = self.get_ppm_corrected(frequency)
                    # print(f"freq {frequency} ppm {self._ppm} -> {frequency + (self._ppm * frequency / 1e6)}")
                logger.info(f"Set frequency {frequency / 1e6:0.6f}MHz")
            except Exception as err:
                self._error = str(err)

    def set_ppm(self, ppm: float) -> None:
        """
        +ve reduces tuned frequency
        -ve increases the tuned frequency

        :param ppm: Parts per million error,
        :return:
        """
        self._ppm = ppm
        self.set_centre_frequency_hz(self._centre_frequency_hz)

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
                self._error = f"failed to set gain of '{gain}', {err}"

    def set_gain_mode(self, mode: str) -> None:
        if mode in self._gain_modes:
            self._gain_mode = mode
            if self._sdr:
                # because the 'best' way to set the mode is to set the gain, apparently
                self.set_gain(self._gain)
        return

    def set_bandwidth_hz(self, bw: float) -> None:
        if self._sdr:
            try:
                self._sdr.set_bandwidth(int(bw))
            except Exception as err:
                self._error += str(err)
            self._bandwidth_hz = self._sdr.get_bandwidth()

    def get_bandwidth_hz(self) -> float:
        if self._sdr:
            self._bandwidth_hz = self._sdr.get_bandwidth()
        return self._bandwidth_hz

    def read_cplx_samples(self, number_samples: int) -> Tuple[np.array, float]:
        """
        Get complex float samples from the device

        Note that we don't use unpack() for this device

        :return: A tuple of a numpy array of complex samples and time in nsec
        """
        complex_data = None
        rx_time = 0

        if self._sdr and self._connected:
            try:
                complex_data = self._sdr.read_samples(number_samples)  # will return np.complex128
                rx_time = self.get_time_ns(number_samples)
                complex_data = np.array(complex_data, dtype=np.complex64)  # (?) we need all values to be 32bit floats
            except Exception as err:
                self._connected = False
                self._error = str(err)
                logger.error(self._error)
                raise ValueError(err)

        return complex_data, rx_time
