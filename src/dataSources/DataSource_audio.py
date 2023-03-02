"""
Audio input wrapper

We expect a stereo input with something external doing a proper IQ split and feeding the left/right audio
inputs.

Configuring the block size seems critical, if it is widely different from the wanted fft size then under
Windows we can just exit python with no exceptions, just a null ptr error code

If we have a mono input we duplicate each sample into both I and Q samples
"""

import logging
import queue
import time
from typing import Tuple

import numpy as np

from dataSources import DataSource

logger = logging.getLogger('spectrum_logger')

module_type = "audio"
help_string = f"{module_type}:Number \t- number of the input device e.g. {module_type}:1, '?' for list"
web_help_string = "Number - number of the input device e.g. 1. Use '?' for list"

try:
    import_error_msg = ""
    import sounddevice as sd
except ImportError as msg:
    sd = None
    import_error_msg = f"Info: {module_type} source has an issue, {str(msg)}"
    logging.info(import_error_msg)


# return an error string if we are not available
def is_available() -> Tuple[str, str]:
    return module_type, import_error_msg


# A queue for the audio streamer callback to put samples in to, 4 deep for low latency
audio_q = queue.Queue(4)


def audio_callback(incoming_samples: np.ndarray, frames: int, time_1, status) -> None:
    if status:
        if status.input_overflow:
            DataSource.write_overflow(1)
            logger.info(f"{module_type} input overflow")
        else:
            err = f"Error: {module_type} had a problem, {status}"
            logger.error(err)

    # make complex array with left/right as real/imaginary
    # you should be feeding the audio LR with a complex source
    # frames is the number of left/right sample pairs, i.e. the samples

    if (incoming_samples is not None) and (frames > 0):
        complex_data = np.empty(shape=(frames,), dtype=np.complex64)

        # handle stereo/mono incoming_samples
        if incoming_samples.shape[1] >= 2:
            for n in range(frames):
                complex_data[n] = complex(incoming_samples[n][0], incoming_samples[n][1])
        else:
            # must be mono
            for n in range(frames):
                complex_data[n] = complex(incoming_samples[n], incoming_samples[n])

        audio_q.put(complex_data.copy())


class Input(DataSource.DataSource):

    def __init__(self,
                 source: str,
                 data_type: str,
                 sample_rate: float,
                 centre_frequency: float,
                 input_bw: float
                 ):
        """
        The audio input source

        :param source: Number of the device to use, or 'L' for a list
        :param data_type: Not used
        :param sample_rate: The sample rate we will set the source to
        :param centre_frequency: Not used
        :param input_bw: The filtering of the input, may not be configurable
        """
        self._constant_data_type = "16tle"
        super().__init__(source, self._constant_data_type, sample_rate, centre_frequency, input_bw)

        self._connected = False
        self._channels = 2  # we are really expecting stereo
        self._device_number = 0  # will be set in open
        self._audio_stream = None
        super().set_help(help_string)
        super().set_web_help(web_help_string)

        # we will read samples from the actual source in a different size from that requested
        # so that we can divorce one from the other, need index to tell where we are
        self._complex_data = None
        self._read_block_size = 2048  #
        self._rx_time = 0  # first sample time

    def open(self) -> bool:
        global import_error_msg
        if import_error_msg != "":
            msgs = f"No {module_type} support available, {import_error_msg}"
            self._error = msgs
            logger.error(msgs)
            raise ValueError(msgs)

        if self._source == "?":
            self._audio_stream = None
            self._error = str(sd.query_devices())
            return False

        try:
            self._device_number = int(self._source)
        except ValueError:
            self._error += f"Illegal audio source number {self._source}"
            logger.error(self._error)
            raise ValueError(self._error)

        try:
            capabilities = sd.query_devices(device=self._device_number)
            if capabilities['max_input_channels'] < 2:
                self._channels = 1
        except Exception as err_msg:
            msgs = f"{module_type} query error: {err_msg}"
            self._error = str(msgs)
            logger.error(msgs)
            raise ValueError(msgs)

        self.bound_sample_rate()
        try:
            self._audio_stream = sd.InputStream(samplerate=self._sample_rate_sps,
                                                device=self._device_number,
                                                channels=self._channels,
                                                callback=audio_callback,
                                                blocksize=self._read_block_size,
                                                dtype="float32")
            self._audio_stream.start()  # required as we are not using 'with'

        except sd.PortAudioError as err_msg:
            msgs = f"{module_type} inputStream error: {err_msg}"
            self._error = str(msgs)
            logger.error(msgs)
            raise ValueError(msgs)  # from None
        except ValueError as err_msg:
            msgs = f"device number {self._source}, {err_msg}"
            self._error = str(msgs)
            logger.error(msgs)
            raise ValueError(msgs)  # from None
        except Exception as err_msg:
            msgs = f"device number {self._source}, {err_msg}"
            self._error = str(msgs)
            logger.error(msgs)
            raise ValueError(msgs)  # from None

        self._sample_rate_sps = self._audio_stream.samplerate  # actual sample rate
        logger.debug(f"Connected to {module_type} {self._device_number}")
        logger.info(f"Audio stream started ")
        self._connected = True

        return self._connected

    def close(self) -> None:
        if self._audio_stream:
            self._audio_stream.stop()
            self._audio_stream.close(ignore_errors=True)
        self._connected = False

    def set_sample_rate_sps(self, sr: float) -> None:
        self._sample_rate_sps = sr
        self.bound_sample_rate()
        # changing sample rate means resetting the audio device
        self.close()
        try:
            self.open()
        except ValueError as msgs:
            self._error = str(msgs)

    def bound_sample_rate(self) -> None:
        try:
            # can't find min/max sample rate allowed so just catch the exception
            sd.check_input_settings(device=self._device_number, samplerate=self._sample_rate_sps)
        except sd.PortAudioError:
            self._error += f"Unsupported audio source sample rate {self._sample_rate_sps / 1e6}Msps, setting 0.048Msps"
            logger.error(self._error)
            self._sample_rate_sps = 48000.0

    def set_sample_type(self, data_type: str) -> None:
        # we can't set a different sample type on this source
        super().set_sample_type(self._constant_data_type)

    def _read_source_samples(self, num_samples: int):
        # read a minimum of num_samples from the queue

        # sounddevice seems to require a reboot quite often before it works on windows,
        # probably driver problems after an OS sleep
        # Count number of queue emtpy events, along with sleep to get an idea if
        # something is broken

        # read blocks until we have at least the required number of samples
        samples_got = 0
        max_wait_count = ((5 * self._sample_rate_sps) / num_samples)  # 5 seconds max wait
        empty_count = max_wait_count
        while samples_got < num_samples:
            try:
                complex_data = audio_q.get(block=False)
                if samples_got == 0:
                    if self._complex_data.size == 0:
                        self._rx_time = self.get_time_ns()
                empty_count = max_wait_count
                self._complex_data = np.append(self._complex_data, complex_data)
                samples_got += complex_data.size
            except queue.Empty:
                time.sleep(num_samples / self._sample_rate_sps)  # how long we expect samples to take to arrive
                empty_count -= 1
                if empty_count <= 0:
                    msgs = f"{module_type} not producing samples"
                    self._error = str(msgs)
                    logger.error(msgs)
                    print(msgs)
                    raise ValueError(msgs)

    def read_cplx_samples(self, number_samples: int) -> Tuple[np.array, float]:
        """
        Get complex float samples from the device
        :return: A tuple of a numpy array of complex samples and time in nsec
        """
        complex_data = None
        rx_time = 0

        if self._connected:
            global audio_q

            # create an empty array to store things if it is not there already
            if self._complex_data is None:
                self._complex_data = np.empty(shape=0, dtype='complex64')

            # do we need to read in more samples
            if number_samples > self._complex_data.size:
                self._read_source_samples(number_samples)

            if self._complex_data.size >= number_samples:
                # get the array we wish to pass back
                complex_data = np.array(self._complex_data[:number_samples], dtype=np.complex64)
                rx_time = self._rx_time

                # drop the used samples
                self._complex_data = np.array(self._complex_data[number_samples:], dtype=np.complex64)
                # following time will be overwritten if the _complex_data is now empty
                self._rx_time += number_samples / self._sample_rate_sps

            self._overflows += DataSource.read_and_reset_overflow()

        return complex_data, rx_time
