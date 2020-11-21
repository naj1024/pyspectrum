"""
Audio input wrapper
"""

import queue
import pprint as pp
from typing import Tuple
import logging
import time

import numpy as np

from dataSources import DataSource

logger = logging.getLogger('spectrum_logger')

module_type = "audio"
help_string = f"{module_type}:Number \t- number of the input device e.g. {module_type}:1, '?' for list"
web_help_string = "Number - number of the input device e.g. 1"

try:
    import_error_msg = ""
    import sounddevice as sd
except ImportError as msg:
    sd = None
    import_error_msg = "Info: audio source has an issue, {str(msg)}"
    logging.info(import_error_msg)


# return an error string if we are not available
def is_available() -> Tuple[str, str]:
    return module_type, import_error_msg


# A queue for the audio streamer callback to put samples in to
audio_q = queue.Queue()


def audio_callback(incoming_samples: np.ndarray, frames: int, time_1, status):
    if status:
        raise ValueError(f"Error: {module_type} had a problem, {status}")

    # make complex array with left/right as real/imaginary
    # this is wrong unless you are feeding the audio LR with a complex source
    # frames is the number of left/right sample pairs, i.e. the samples
    complex_data = np.zeros(shape=(frames,), dtype=np.complex64)
    for n in range(frames):
        complex_data[n] = complex(incoming_samples[n][0], incoming_samples[n][1])
    audio_q.put(complex_data.copy())


class Input(DataSource.DataSource):

    def __init__(self,
                 source: str,
                 number_complex_samples: int,
                 data_type: str,
                 sample_rate: float,
                 centre_frequency: float,
                 sleep_time: float):
        """
        The audio input source

        :param source: Number of the device to use, or 'L' for a list
        :param number_complex_samples: The number of complex samples we require each request
        :param data_type: Not used
        :param sample_rate: The sample rate we will set the source to
        :param centre_frequency: Not used
        :param sleep_time: Time in seconds between reads, not used on most sources
        """
        self._constant_data_type = "16tle"
        super().__init__(source, number_complex_samples, self._constant_data_type, sample_rate, centre_frequency, sleep_time)
        self.bound_sample_rate()

        self._connected = False
        self._device_number = 0
        self._audio_stream = None

    def open(self):
        global import_error_msg
        if import_error_msg != "":
            msgs = f"{module_type} Error: No {module_type} support available, {import_error_msg}"
            self._error = msgs
            logger.error(msgs)
            raise ValueError(msgs)

        if self._source == "?":
            self._audio_stream = None
            print("Audio devices available:")
            pp.pprint(sd.query_devices())
            return

        try:
            self._device_number = int(self._source)
            self._audio_stream = sd.InputStream(samplerate=self._sample_rate,
                                                device=self._device_number,
                                                channels=2, callback=audio_callback,
                                                blocksize=self._number_complex_samples,  # NOTE the size, not zero
                                                dtype="float32")
            self._audio_stream.start()  # required as we are not using 'with'
            self._sample_rate = self._audio_stream.samplerate  # actual sample rate
            logger.info("Audio stream started")
            logger.debug(f"Connected to {module_type} {self._device_number}")
            self._connected = True

        except sd.PortAudioError as err_msg:
            msgs = f"{module_type} error: {err_msg}"
            self._error = str(msgs)
            logger.error(msgs)
            raise ValueError(msgs) # from None
        except ValueError as err_msg:
            msgs = f"Error: {module_type} device number {self._source}, {err_msg}"
            self._error = str(msgs)
            logger.error(msgs)
            raise ValueError(msgs) # from None

    def close(self):
        if self._audio_stream:
            self._audio_stream.stop()
            self._audio_stream.close(ignore_errors=True)
        self._connected = False

    def connect(self) -> bool:
        # as we can list available then we may have to die here if someone asks us to connect to "?"
        if not self._audio_stream:
            if self._source != "?":
                self._error = f"No such audio device as {self._source}"
                logger.error(f"No such audio device as {self._source}")
        return self._connected

    def get_help(self):
        return help_string

    def get_web_help(self):
        return web_help_string

    def set_sample_rate(self, sr: float):
        self._sample_rate = sr
        self.bound_sample_rate()
        # changing sample rate means resetting the audio device
        self.close()
        try:
            self.open()
        except ValueError as msgs:
            self._error = str(msgs)

    def bound_sample_rate(self):
        # TODO: find max sample rate and set that as the limit
        if self._sample_rate > 250.0e3:
            self._sample_rate = 250000.0
            self._error = "Audio source sample rate too high, setting 250kHz"
            logger.error("Audio source sample rate too high, setting 250kHz")
        elif self._sample_rate < 1.0e3:
            self._sample_rate = 1000.0
            self._error = "Audio source sample rate too low, setting 1kHz"
            logger.error("Audio source sample rate too low, setting 1kHz")

    def set_sample_type(self, data_type: str):
        # we can't set a different sample type on this source
        super().set_sample_type(self._constant_data_type)

    def read_cplx_samples(self) -> Tuple[np.array, float]:
        """
        Get complex float samples from the device
        :return: A tuple of a numpy array of complex samples and time in nsec
        """
        if self._connected:
            global audio_qs
            complex_data = audio_q.get()
            return complex_data, self.get_time_ns()
        else:
            return (None, 0.0)
