"""
Audio input wrapper

We expect a stereo input with something external doing a proper IQ split and feeding the left/right audio
inputs.

If we have a mono input we duplicate each sample into both I and Q samples
"""

import queue
import pprint as pp
import logging
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
    import_error_msg = "Info: audio source has an issue, {str(msg)}"
    logging.info(import_error_msg)


# return an error string if we are not available
def is_available() -> Tuple[str, str]:
    return module_type, import_error_msg


# A queue for the audio streamer callback to put samples in to, 4 deep for low latency
audio_q = queue.Queue(4)


def audio_callback(incoming_samples: np.ndarray, frames: int, time_1, status) -> None:
    if status:
        if status.input_overflow:
            logger.error("audio input overflow")
        else:
            err = f"Error: {module_type} had a problem, {status}"
            logger.error(err)
            raise ValueError(err)

    # make complex array with left/right as real/imaginary
    # you should be feeding the audio LR with a complex source
    # frames is the number of left/right sample pairs, i.e. the samples
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
                 number_complex_samples: int,
                 data_type: str,
                 sample_rate: float,
                 centre_frequency: float,
                 input_bw: float
                 ):
        """
        The audio input source

        :param source: Number of the device to use, or 'L' for a list
        :param number_complex_samples: The number of complex samples we require each request
        :param data_type: Not used
        :param sample_rate: The sample rate we will set the source to
        :param centre_frequency: Not used
        :param input_bw: The filtering of the input, may not be configurable
        """
        self._constant_data_type = "16tle"
        super().__init__(source, number_complex_samples, self._constant_data_type, sample_rate,
                         centre_frequency, input_bw)

        self._connected = False
        self._channels = 2  # we are really expecting stereo
        self._device_number = 0  # will be set in open
        self._audio_stream = None
        super().set_help(help_string)
        super().set_web_help(web_help_string)

        # sounddevice seems to require a reboot quite often before it works on windows,
        # probably driver problems after an OS sleep
        # Count number of queue emtpy events, along with sleep to get an idea if
        # something is broken
        self._empty_count = 0

    def open(self) -> bool:
        global import_error_msg
        if import_error_msg != "":
            msgs = f"No {module_type} support available, {import_error_msg}"
            self._error = msgs
            logger.error(msgs)
            raise ValueError(msgs)

        if self._source == "?":
            self._audio_stream = None
            print("Audio devices available:")
            pp.pprint(sd.query_devices())
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
                                                blocksize=self._number_complex_samples,  # NOTE the size, not zero
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
            self._error += f"Unsupported audio source sample rate {self._sample_rate_sps/1e6}Msps, setting 0.048Msps"
            logger.error(self._error)
            self._sample_rate_sps = 48000.0

    def set_sample_type(self, data_type: str) -> None:
        # we can't set a different sample type on this source
        super().set_sample_type(self._constant_data_type)

    def read_cplx_samples(self) -> Tuple[np.array, float]:
        """
        Get complex float samples from the device
        :return: A tuple of a numpy array of complex samples and time in nsec
        """
        complex_data = None
        rx_time = 0

        if self._connected:
            global audio_q
            try:
                complex_data = audio_q.get(block=False)
                rx_time = self.get_time_ns()
                self._empty_count = 0
            except queue.Empty:
                time.sleep(0.001)
                self._empty_count += 1
                if self._empty_count > 10000:
                    msgs = f"{module_type} not producing samples, reboot required?"
                    self._error = str(msgs)
                    logger.error(msgs)
                    print(msgs)
                    self._empty_count = 0
                    raise ValueError(msgs)

        return complex_data, rx_time
