"""
Soapy class wrapper

"""

import numpy as np
from typing import Tuple
import logging
import time

from dataSources import DataSource

logger = logging.getLogger('spectrum_logger')

module_type = "soapy"
help_string = f"{module_type}:Name \t- Name is soapy driver, e.g. {module_type}:?, {module_type}:sdrplay"

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
                 centre_frequency: float):
        """
        The soapy input source

        :param source: Name of the soapy driver to use
        :param number_complex_samples: The number of complex samples we require each request
        :param data_type: Not required, we set complex 32f
        :param sample_rate: The sample rate we will set the source to
        :param centre_frequency: The centre frequency the source will be set to
        """
        super().__init__(source, number_complex_samples, data_type, sample_rate, centre_frequency)

        global import_error_msg
        if import_error_msg != "":
            msgs = f"{module_type} Error: No {module_type} support available, {import_error_msg}"
            logger.error(msgs)
            raise ValueError(msgs)

        try:
            if self._source == "?":
                self._sdr = None
                results = SoapySDR.Device.enumerate()
                print("Soapy drivers:")
                for result in results:
                    print(result)
                return
            self._sdr = SoapySDR.Device(f'driver={self._source}')
        except Exception as msg_err:
            msgs = f"{module_type} {msg_err}"
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
            self._sdr.setSampleRate(SoapySDR.SOAPY_SDR_RX, self._channel, self._sample_rate)
            self._sdr.setFrequency(SoapySDR.SOAPY_SDR_RX, self._channel, self._centre_frequency)
            self._rx_stream = self._sdr.setupStream(SoapySDR.SOAPY_SDR_RX, SoapySDR.SOAPY_SDR_CF32)

            # Set Automatic Gain Control
            if self._sdr.hasGainMode(SoapySDR.SOAPY_SDR_RX, self._channel):
                logger.info("Soapy setting AGC")
                self._sdr.setGainMode(SoapySDR.SOAPY_SDR_RX, self._channel, True)

            # turn on the stream
            self._sdr.activateStream(self._rx_stream)  # start streaming
        except Exception as err_msg:
            msgs = f"{module_type} {err_msg}"
            logger.error(msgs)
            raise ValueError(msgs) from None

        # print(self._sdr.getSampleRate(SoapySDR.SOAPY_SDR_RX, self._channel))
        logger.debug(f"{module_type}: {self._centre_frequency / 1e6:.6}MHz @ {self._sample_rate:.3f}sps")

        self._connected = True

    def connect(self) -> bool:
        # as we can list available then we may have to die here if someone asks us to connect to "?"
        if not self._sdr:
            if self._source != "?":
                print(f"No such soapy device as {self._source}")
            quit()
        return self._connected

    def close(self) -> None:
        if self._sdr:
            self._sdr.deactivateStream(self._rx_stream)  # stop streaming
            self._sdr.closeStream(self._rx_stream)
            self._sdr = None

    def read_cplx_samples(self) -> Tuple[np.array, float]:
        """
        Get complex float samples from the device

        :return: A tuple of a numpy array of complex samples and time in nsec
        """

        # Receive all samples
        index = 0
        wait = 10
        rx_time = 0
        while index < self._output_size:
            # readStream() doesn't seem to be a blocking call
            read = self._sdr.readStream(self._rx_stream, [self._tmp], self._tmp_size, timeoutUs=1000000)

            # set time stamp as first set of samples provided
            if index == 0:
                rx_time = time.time_ns()
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
