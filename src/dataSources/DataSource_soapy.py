"""
Soapy class wrapper

This has really only been tested on an sdrplay & rtlsdr. Things that are probably specific are:
    1. sdrplay gains seems to be upside down, i.e. its an attenuator

On Linux, debian bullseye ():
    apt install python3-soapysdr
    dpkg -L python3-soapysdr

    If using virtual environments then copy the files in dist-packages (.py and .so) to your
    virtual environments site-packages
        cp /usr/lib/python3/dist-packages/SoapySDR.py
            /home/username/.local/share/virtualenvs/username-w79atRX8/lib/python3.9/site-packages/
        cp /usr/lib/python3/dist-packages/_SoapySDR.cpython-39-x86_64-linux-gnu.so
            /home/username/.local/share/virtualenvs/username-w79atRX8/lib/python3.9/site-packages/

    For rtlsdr you may need to blacklist the use of dvb which will claim the rtlsdr
    create no-dvb.conf in /etc/modprobe.d with contents:

        blacklist dvb_usb_rtl28xxu
        blacklist rtl2832
        blacklist rtl2830

"""

import logging
import time
from typing import Tuple

import numpy as np

from dataSources import DataSource

logger = logging.getLogger('spectrum_logger')

module_type = "soapy"
help_string = f"{module_type}:Name \t- Name is soapy driver, e.g. {module_type}:?, {module_type}:sdrplay"
web_help_string = "Name - Name is soapy driver, e.g. sdrplay. Use '?' for list"

try:
    import_error_msg = ""
    import SoapySDR
except (ImportError, ValueError) as msg:
    SoapySDR = None
    import_error_msg = f"{module_type} source has an issue, " + str(msg)
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
        The soapy input source

        :param parameters: Name of the soapy driver to use
        :param data_type: Not required, we set complex 32f
        :param sample_rate: The sample rate we will set the source to
        :param centre_frequency: The centre frequency the source will be set to
        :param input_bw: The filtering of the input, may not be configurable
        """
        self._constant_data_type = "32fle"
        if not parameters or parameters == "":
            parameters = "rtlsdr"  # default
        super().__init__(parameters, self._constant_data_type, sample_rate, centre_frequency, input_bw)
        self._name = module_type
        self._connected = False
        self._sdr = None
        self._channel = 0  # we will use channel zero for now
        # soapy has quite large read blocks, so read a complete block at a time
        self._complex_data = None
        self._block_read_size = 0
        self._rx_time = 0
        self._buffer_rx_time = 0
        self._soapyMTU = 0
        self._index = -1
        self._rx_stream = None
        self._gain_modes = []
        self._gain_mode = "auto"
        self._max_gain: float = 100
        self._min_gain: float = 0.0
        # not correctly setting min,max on sps and freq yet
        self._min_sps: float = 0.0
        self._max_sps: float = 8e6
        self._allowed_sps = []
        self._min_cf: float = 50.0e6
        self._max_cf: float = 1.0e9
        self._allowed_bws = []
        super().set_help(help_string)
        super().set_web_help(web_help_string)

    def open(self) -> bool:
        global import_error_msg
        if import_error_msg != "":
            msgs = f"{module_type} {self._parameters} no support available, {import_error_msg}"
            self._error = msgs
            logger.error(msgs)
            raise ValueError(msgs)

        try:
            if self._parameters == "?":
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
            self._sdr = SoapySDR.Device(f'driver={self._parameters}')
        except Exception as msg_err:
            msgs = f"{module_type} {self._parameters} open error, {msg_err}"
            self._error = str(msgs)
            logger.error(msgs)
            raise ValueError(msgs)

        self._channel = 0  # we will use channel zero for now

        logger.debug(f"Connected to {module_type} {self._parameters} using channel {self._channel}")
        # for sr in self._sdr.listSampleRates(SoapySDR.SOAPY_SDR_RX, self._channel):
        #     pp.pprint(sr)

        # NOTE soapy may not range check any values, may just go quiet and give no samples
        try:
            # Set Automatic Gain Control
            if self._sdr.hasGainMode(SoapySDR.SOAPY_SDR_RX, self._channel):
                self._gain_modes = ["manual", "auto"]  # what we will call them
                self.get_gain_mode()  # leave gain mode as is
                self.get_gain()
                # and what can we set things to
                gains = self._sdr.getGainRange(SoapySDR.SOAPY_SDR_RX, self._channel)
                self._min_gain = gains.minimum()
                self._max_gain = gains.maximum()
                logger.info(f"{module_type} {self._parameters} gain range {self._min_gain} to {self._max_gain}")
            else:
                logger.info(f"{module_type} {self._parameters} has no gain mode")

            # ranges may return different types of thing
            # could be a:
            #    tuple of SoapySDR.Range with multiple ranges of say 8000,8000 then 16000,16000
            #    tuple of SoapySDR.Range with a single range like 0,6e9
            #    a SoapySDR.Range, i.e. not a tuple of them
            #
            # sr_range = self._sdr.getSampleRateRange(SoapySDR.SOAPY_SDR_RX, self._channel)
            # for sr in sr_range:
            #     print(f"sr: {sr.minimum()} {sr.maximum()}")
            # self._min_sps = sr_range.minimum()
            # self._max_sps = sr_range.maximum
            #
            # probably sdrplay specific
            sr_list = self._sdr.listSampleRates(SoapySDR.SOAPY_SDR_RX, self._channel)
            allowed_srs = set()
            for sr in sr_list:
                allowed_srs.add(sr)
            self._allowed_sps = list(allowed_srs)
            self._allowed_sps.sort()
            logger.info(f"{module_type} {self._parameters} samples rates {self._allowed_sps}")

            # probably sdrplay specific
            # find min and max centre frequencies
            cf_range = self._sdr.getFrequencyRange(SoapySDR.SOAPY_SDR_RX, self._channel)
            for cf in cf_range:
                if cf.minimum() < self._min_cf:
                    self._min_cf = cf.minimum()
                if cf.maximum() > self._max_cf:
                    self._max_cf = cf.maximum()
            logger.info(f"{module_type} {self._parameters} cf min {self._min_cf}, max {self._max_cf}")

            self.get_ppm()

            # probably sdrplay specific
            bw_list = self._sdr.listBandwidths(SoapySDR.SOAPY_SDR_RX, self._channel)  # tuple, min to max
            allowed_bws = set()
            for bw in bw_list:
                allowed_bws.add(bw)
            self._allowed_bws = list(allowed_bws)
            self._allowed_bws.sort()
            logger.info(f"{module_type} {self._parameters} bandwidths {self._allowed_bws}")

            self.get_bandwidth_hz()

            logger.info(f"setting sps {self._sample_rate_sps}")
            self.set_sample_rate_sps(self._sample_rate_sps)
            logger.info(f"set sps {self._sample_rate_sps}")
            self.set_centre_frequency_hz(self._centre_frequency_hz)
            self._rx_stream = self._sdr.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)

            # turn on the stream
            self._sdr.activateStream(self._rx_stream)  # start streaming

            # create buffer for soapy buffers to be written into
            self._soapyMTU = self._sdr.getStreamMTU(self._rx_stream)
            logger.debug(f"Soapy buffer MTU {self._soapyMTU}")

            self._complex_data = np.array([0] * self._soapyMTU, np.complex64)
            self._index = self._soapyMTU  # force read on first pass

        except Exception as err_msg:
            msgs = f"{module_type} {self._parameters} configuration problem, {err_msg}"
            logger.error(msgs)
            raise ValueError(msgs) from None

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

    def set_sample_rate_sps(self, sr: float) -> None:
        logger.info("set_sample_rate_sps()")
        if self._sdr:
            # find an allowed sr from the set
            min_sr = max(self._allowed_sps)
            for asr in self._allowed_sps:
                if asr >= sr:
                    min_sr = asr
                    break
            self._rx_time = 0
            self._sample_rate_sps = min_sr
            self._sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, self._channel, self._sample_rate_sps)
            self.get_sample_rate_sps()
            logger.info(f"Set sample rate {sr}sps as {self._sample_rate_sps}sps")

    def get_centre_frequency_hz(self) -> float:
        if self._sdr:
            # if this object is compensating we can't ask the front end
            if self._hw_ppm_compensation:
                self._centre_frequency_hz = self._sdr.getFrequency(SoapySDR.SOAPY_SDR_RX, self._channel)
        return self._centre_frequency_hz

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
                    self._centre_frequency_hz = self._min_cf
                elif freq > self._max_cf:
                    freq = self._max_cf
                    self._centre_frequency_hz = self._max_cf
                else:
                    self._centre_frequency_hz = cf  # non compensated frequency
                self._sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, self._channel, freq)
                set_freq = self._sdr.getFrequency(SoapySDR.SOAPY_SDR_RX, self._channel)
                if set_freq != freq:
                    print(f"failed to set freq {set_freq} != {freq}")

    def set_sample_type(self, data_type: str) -> None:
        # we can't set a different sample type on this source
        super().set_sample_type(self._constant_data_type)

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
                    self._gain_mode = "manual"
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
                # find a bw
                for bw_entry in self._allowed_bws:
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

    def read_cplx_samples(self, number_samples: int) -> Tuple[np.array, float]:
        """
        Get complex float samples from the device

        Note that we don't use unpack() for this device

        Always read exactly what we are asked for

        :return: A tuple of a numpy array of complex samples and time in nsec
        """
        complex_data = None

        if self._connected:
            amount_read = 0
            complex_data = np.array([0] * number_samples, np.complex64)
            while amount_read < number_samples:
                # do we need to read in the next block from soapy
                if self._index >= self._block_read_size:
                    try:
                        read_status = self._sdr.readStream(self._rx_stream, [self._complex_data],
                                                           len(self._complex_data), timeoutUs=2000000)
                        # did anything go wrong
                        if read_status.ret < 0:
                            if read_status.ret == -4:
                                self._overflows += 1
                                self._error = f"{module_type} {read_status.ret} read overflow error"
                            else:
                                self._error = f"{module_type} {read_status.ret} read other error"
                            logger.error(self._error)
                            return None, 0
                        elif read_status.ret == 0:
                            self._error = f"{module_type} {read_status.ret} empty read"
                            logger.error(self._error)
                            return None, 0
                        else:
                            # arghhhh sometimes we get less than we want
                            self._block_read_size = read_status.ret
                            # if self._block_read_size != self._soapyMTU:
                            #     self._error = f"{module_type} {read_status.ret} short read, not self._soapyMTU"
                            #     logger.error(self._error)

                            # soapy has timestamps (read_status.timeNs), but they don't change when using eg rtlsdr
                            # so just going to ignore them and get a local time
                            self._buffer_rx_time = time.time_ns()

                            self._index = 0

                    except Exception as err:
                        self._connected = False
                        self._error = str(err)
                        logger.error(self._error)
                        raise ValueError(err)

                # how many can we read from our buffer
                num_available = self._block_read_size - self._index
                num_to_use = num_available
                if num_available >= (number_samples - amount_read):
                    num_to_use = number_samples - amount_read

                # copy into output buffer
                complex_data[amount_read:(amount_read + num_to_use)] = self._complex_data[
                                                                       self._index:(self._index + num_to_use)]
                # print(f"need {number_samples} data[{amount_read}:{amount_read+num_to_use}] = "
                #       f"cd[{self._index}:{self._index+num_to_use}] from {self._block_read_size}")

                # work out the time of our samples from the beginning of the block
                if amount_read == 0:
                    self._rx_time = self._buffer_rx_time + ((1e9 * self._index) / self._sample_rate_sps)

                amount_read += num_to_use
                self._index += num_to_use  # index gets reset on every block read

            # soapy read_status.ret error codes
            # SOAPY_SDR_TIMEOUT -1
            # SOAPY_SDR_STREAM_ERROR -2
            # SOAPY_SDR_CORRUPTION -3
            # SOAPY_SDR_OVERFLOW -4   <- i.e. buffers are overflowing because can't read fast enough
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

        return complex_data, self._rx_time
