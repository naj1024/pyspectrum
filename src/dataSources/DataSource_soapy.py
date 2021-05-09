"""
Soapy class wrapper

This has really only been tested on an sdrplay. Things that are probably specific are:
    1. bws are a discrete set
    2. there is no hardware ppm, soapy says there is but then fails to set it, don't actually know of sdrplay has ppm
    3. sdrplay gains seems to be upside down, i.e. its an attenuator
    4. sdrplay gains are from zero to 42 as a max/min range not discrete
    5. don't yet check for proper ranges on freq or sample rate, soapy will silently ignore wrong ones

On Linux, debian bullseye ():
    apt install python3-soapysdr
    dpkg -L python3-soapysdr

    Copy the files in dist-packages (.py and .so) to your virtual environments site-packages
    cp /usr/lib/python3/dist-packages/SoapySDR.py
            /home/username/.local/share/virtualenvs/username-w79atRX8/lib/python3.9/site-packages/
    cp /usr/lib/python3/dist-packages/_SoapySDR.cpython-39-x86_64-linux-gnu.so
            /home/username/.local/share/virtualenvs/username-w79atRX8/lib/python3.9/site-packages/
"""

import numpy as np
from typing import Tuple
import logging

from dataSources import DataSource

logger = logging.getLogger('spectrum_logger')

module_type = "soapy"
help_string = f"{module_type}:Name \t- Name is soapy driver, e.g. {module_type}:?, {module_type}:sdrplay"
web_help_string = "Name - Name is soapy driver, e.g. sdrplay. Use '?' for list"

try:
    import_error_msg = ""
    import SoapySDR
except ImportError as msg:
    SoapySDR = None
    import_error_msg = f"{module_type} source has an issue, {str(msg)}"
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
        The soapy input source

        :param source: Name of the soapy driver to use
        :param number_complex_samples: The number of complex samples we require each request
        :param data_type: Not required, we set complex 32f
        :param sample_rate: The sample rate we will set the source to
        :param centre_frequency: The centre frequency the source will be set to
        :param input_bw: The filtering of the input, may not be configurable
        """
        super().__init__(source, number_complex_samples, data_type, sample_rate, centre_frequency, input_bw)
        self._connected = False
        self._sdr = None
        self._channel = 0  # we will use channel zero for now
        self._tmp = None
        self._tmp_size = 0
        self._complex_data = None
        self._output_size = 0
        self._rx_stream = None
        self._gain_modes = []
        self._gain_mode = "auto"
        self._max_gain = 100
        self._min_gain = 0
        # not correctly setting min,max on sps and freq yet
        self._min_sps = 0
        self._max_sps = 8e6
        self._min_cf = 0
        self._max_cf = 2e9
        super().set_help(help_string)
        super().set_web_help(web_help_string)

    def open(self) -> bool:
        global import_error_msg
        if import_error_msg != "":
            msgs = f"No {module_type} support available, {import_error_msg}"
            self._error = msgs
            logger.error(msgs)
            raise ValueError(msgs)

        try:
            if self._source == "?":
                self._sdr = None
                devices = SoapySDR.Device.enumerate()
                print("Soapy devices:")
                for device in devices:
                    print(device)
                    for key, value in device.items():
                        if key == 'driver':
                            self._error += f"{str(value)}\n"
                return False
        except Exception as msg_err:
            msgs = f"{module_type} {msg_err}"
            self._error = str(msgs)
            logger.error(msgs)
            raise ValueError(msgs)

        try:
            self._sdr = SoapySDR.Device(f'driver={self._source}')
        except Exception as msg_err:
            msgs = f"{module_type} {msg_err}"
            self._error = str(msgs)
            logger.error(msgs)
            raise ValueError(msgs)

        self._channel = 0  # we will use channel zero for now

        logger.debug(f"Connected to {module_type}")
        # for sr in self._sdr.listSampleRates(SoapySDR.SOAPY_SDR_RX, self._channel):
        #     pp.pprint(sr)

        # Create numpy array for received samples, for reading into as we can get partial reads
        self._tmp = np.array([0] * self._number_complex_samples, np.complex64)
        self._tmp_size = self._tmp.size

        # Create numpy array for received samples, for output
        self._complex_data = np.array([0] * self._number_complex_samples, np.complex64)
        self._output_size = self._complex_data.size

        # NOTE soapy may not range check any values, may just go quiet and give no samples
        try:
            self._sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, self._channel, self._sample_rate_sps)
            self._sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, self._channel, self._centre_frequency_hz)
            self._rx_stream = self._sdr.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)

            # Set Automatic Gain Control
            if self._sdr.hasGainMode(SoapySDR.SOAPY_SDR_RX, self._channel):
                self._gain_modes = ["manual", "auto"]  # what we will call them
                self.get_gain_mode()  # leave gain mode as is
                self.get_gain()
                # and what can we set things to
                gains = self._sdr.getGainRange(SoapySDR.SOAPY_SDR_RX, self._channel)
                self._max_gain = gains.maximum()
                self._min_gain = gains.minimum()

            # ranges may return different types of thing
            # could be a:
            #    tuple of SoapySDR.Range with multiple ranges of say 8000,8000 then 16000,16000
            #    tuple of SoapySDR.Range with a single range like 0,6e9
            #    a SoapySDR.Range, i.e. not a tuple of them
            #
            # sr_range = self._sdr.getSampleRateRange(SoapySDR.SOAPY_SDR_RX, self._channel)
            # print(f"sr range; {sr_range}")
            # self._min_sps = sr_range.minimum()
            # self._max_sps = sr_range.maximum()

            # cf_range = self._sdr.getFrequencyRange(SoapySDR.SOAPY_SDR_RX, self._channel)
            # print(f"cf range; {cf_range}")
            # self._min_cf = cf_range.minimum()
            # self._max_cf = cf_range.maximum()

            self.get_ppm()
            self.get_bandwidth_hz()

            # turn on the stream
            self._sdr.activateStream(self._rx_stream)  # start streaming
        except Exception as err_msg:
            msgs = f"{module_type} {err_msg}"
            logger.error(msgs)
            raise ValueError(msgs) from None

        # print(self._sdr.getSampleRate(SoapySDR.SOAPY_SDR_RX, self._channel))
        logger.debug(f"{module_type}: {self._centre_frequency_hz / 1e6:.6}MHz @ {self._sample_rate_sps:.3f}sps")

        self._connected = True

        return self._connected

    def close(self) -> None:
        if self._sdr:
            self._sdr.deactivateStream(self._rx_stream)  # stop streaming
            self._sdr.closeStream(self._rx_stream)
            self._sdr = None

    def get_sample_rate_sps(self) -> float:
        if self._sdr:
            self._sample_rate_sps = self._sdr.getSampleRate(SoapySDR.SOAPY_SDR_RX, self._channel)
        return self._sample_rate_sps

    def get_centre_frequency_hz(self) -> float:
        if self._sdr:
            # if this object is compensating we can't ask the front end
            if self._hw_ppm_compensation:
                self._centre_frequency_hz = self._sdr.getFrequency(SoapySDR.SOAPY_SDR_RX, self._channel)
        return self._centre_frequency_hz

    def set_sample_rate_sps(self, sr: float) -> None:
        if self._sdr:
            if sr < self._min_sps:
                self._sample_rate_sps = self._min_sps
            elif sr > self._max_sps:
                self._sample_rate_sps = self._max_sps
            else:
                self._sample_rate_sps = sr
            self._sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, self._channel, self._sample_rate_sps)
            self.get_sample_rate_sps()

    def set_centre_frequency_hz(self, cf: float) -> None:
        if self._sdr:
            if self._hw_ppm_compensation:
                if cf < self._min_cf:
                    self._centre_frequency_hz = self._min_cf
                elif cf > self._max_cf:
                    self._centre_frequency_hz = self._max_cf
                else:
                    self._centre_frequency_hz = cf
                self._sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, self._channel, self._centre_frequency_hz)
                self.get_centre_frequency_hz()
            else:
                self._centre_frequency_hz = cf  # non compensated frequency
                freq = self.get_ppm_corrected(cf)
                if freq < self._min_cf:
                    freq = self._min_cf
                elif freq > self._max_cf:
                    freq = self._max_cf
                self._sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, self._channel, freq)
                set_freq = self._sdr.getFrequency(SoapySDR.SOAPY_SDR_RX, self._channel)
                if set_freq != freq:
                    print(f"failed to set freq {set_freq} != {freq}")
                else:
                    print("set freq")

    def get_gain(self) -> float:
        if self._sdr:
            if self._sdr.hasGainMode(SoapySDR.SOAPY_SDR_RX, self._channel):
                self._gain = self._sdr.getGain(SoapySDR.SOAPY_SDR_RX, self._channel)
        return self._gain

    def set_gain(self, gain: float) -> None:
        self._gain = float(gain)
        if self._sdr:
            if self._sdr.hasGainMode(SoapySDR.SOAPY_SDR_RX, self._channel):
                if self._gain > self._max_gain:
                    self._gain = self._max_gain
                if self._gain < self._min_gain:
                    self._gain = self._min_gain
                self._sdr.setGain(SoapySDR.SOAPY_SDR_RX, self._channel, self._gain)

    def get_gain_mode(self) -> str:
        if self._sdr:
            if self._sdr.hasGainMode(SoapySDR.SOAPY_SDR_RX, self._channel):
                on = self._sdr.getGainMode(SoapySDR.SOAPY_SDR_RX, self._channel)
                if on:
                    self._gain_mode = "auto"
                else:
                    self._gain_mode = "false"
        return self._gain_mode

    def set_gain_mode(self, mode: str) -> None:
        if mode in self._gain_modes:
            self._gain_mode = mode
            if self._sdr:
                if self._sdr.hasGainMode(SoapySDR.SOAPY_SDR_RX, self._channel):
                    if self._gain_mode == "auto":
                        self._sdr.setGainMode(SoapySDR.SOAPY_SDR_RX, self._channel, True)
                    else:
                        self._sdr.setGainMode(SoapySDR.SOAPY_SDR_RX, self._channel, False)

    def get_ppm(self) -> float:
        if self._sdr:
            if self._hw_ppm_compensation:
                try:
                    if self._sdr.hasFrequencyCorrection(SoapySDR.SOAPY_SDR_RX, self._channel):
                        self._ppm = self._sdr.getFrequencyCorrection(SoapySDR.SOAPY_SDR_RX, self._channel)
                except AttributeError:
                    self._hw_ppm_compensation = False
        return self._ppm

    def set_ppm(self, ppm: float) -> None:
        self._ppm = ppm
        if self._sdr:
            # depends on if we can change the hw or not
            try:
                if self._sdr.hasFrequencyCorrection(SoapySDR.SOAPY_SDR_RX, self._channel):
                    self._sdr.setFrequencyCorrection(SoapySDR.SOAPY_SDR_RX, self._channel, self._ppm)
                    # did it get set
                    self.get_ppm()
                    if self._ppm != ppm:
                        self._hw_ppm_compensation = False
                        self._ppm = ppm
            except AttributeError:
                self._hw_ppm_compensation = False
            self.set_centre_frequency_hz(self._centre_frequency_hz)

    def set_bandwidth_hz(self, bw: float) -> None:
        if self._sdr:
            try:
                # find a bw, bws is a tuple of floats here - which may be empty
                bws = self._sdr.listBandwidths(SoapySDR.SOAPY_SDR_RX, self._channel)  # tuple, min to max
                for bw_entry in bws:
                    self._bandwidth_hz = bw_entry
                    if bw_entry >= bw:
                        break  # take first BW above what we require
                self._sdr.setBandwidth(SoapySDR.SOAPY_SDR_RX, self._channel, self._bandwidth_hz)
            except AttributeError:
                pass

    def get_bandwidth_hz(self) -> float:
        if self._sdr:
            try:
                self._bandwidth_hz = self._sdr.getBandwidth(SoapySDR.SOAPY_SDR_RX, self._channel)
            except AttributeError:
                pass
        return self._bandwidth_hz

    def read_cplx_samples(self) -> Tuple[np.array, float]:
        """
        Get complex float samples from the device

        Note that we don't use unpack() for this device

        :return: A tuple of a numpy array of complex samples and time in nsec
        """
        rx_time = 0
        # Soapy uses self._complex_data why ?

        if not self._connected:
            return None, 0
        else:
            # Receive all samples
            index = 0
            wait = 10
            while index < self._output_size:
                # readStream() doesn't seem to be a blocking call
                read = self._sdr.readStream(self._rx_stream, [self._tmp], self._tmp_size, timeoutUs=1000000)

                # set time stamp as first set of samples provided
                if index == 0:
                    rx_time = self.get_time_ns()
                    if read.timeNs != 0:
                        rx_time = read.timeNs  # supported in some sdr drivers, but mostly not

                # return code +ve is number of samples
                # return code -ve is error
                # return code zero is try again
                if read.ret == 0:
                    # if we are timing out then return if this happens too often - allows a programme to terminate
                    wait -= 1
                    if not wait:
                        zeros = np.array([0] * self._number_complex_samples, np.complex64)
                        return zeros, rx_time
                if read.ret > 0:
                    wait = 10
                    # copy into output buffer
                    self._complex_data[index:index + read.ret] = self._tmp[:min(read.ret, self._output_size - index)]
                    index += read.ret
                elif read.ret < 0:
                    zeros = np.array([0] * self._number_complex_samples, np.complex64)
                    self._error = f"SoapySDR {read.ret} {SoapySDR.SoapySDR_errToStr(read.ret)}"
                    logger.error(f"SoapySDR {read.ret} {SoapySDR.SoapySDR_errToStr(read.ret)}")
                    return zeros, rx_time

                # read.ret error codes
                # SOAPY_SDR_TIMEOUT -1
                # SOAPY_SDR_STREAM_ERROR -2
                # SOAPY_SDR_CORRUPTION -3
                # SOAPY_SDR_OVERFLOW -4   <- i.e. buffers are over flowing because cant read fast enough
                # SOAPY_SDR_NOT_SUPPORTED -5
                # SOAPY_SDR_TIME_ERROR -6
                # SOAPY_SDR_UNDERFLOW -7

                # read.flags bits
                # SOAPY_SDR_END_BURST 2
                # SOAPY_SDR_HAS_TIME 4
                # SOAPY_SDR_END_ABRUPT 8
                # SOAPY_SDR_ONE_PACKET 16
                # SOAPY_SDR_MORE_FRAGMENTS 32
                # SOAPY_SDR_WAIT_TRIGGER 64

        return self._complex_data, rx_time
