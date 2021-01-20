"""
For saving samples to file

We will store samples in a wrap round buffer which is sized according to the pre-trigger depth required.
When triggered to start writing to file we will output the pre-trigger depth first

Output sample type will be signed 16bit little endian with the filename set to give meta data.

TODO: implement the wrap round buffer for pre-trigger samples
TODO: maybe add .wav output type
todo: implement this as a memory buffer so we don't spend time writting to disk until the end
"""

import time
import logging
import tempfile
import os

import numpy as np

from misc import SnapVariables

logger = logging.getLogger('spectrum_logger')


class FileOutput:
    """
    Simple wrapper class for writing binary data to file
    """

    def __init__(self, config: SnapVariables, centre_frequency_hz: float, sample_rate_sps: float):
        """
        Configure the snapshot

        :param config: How the snap is configured
        :param centre_frequency_hz: Where we are currently tuned to
        :param sample_rate_sps: What the current sample rate is
        """
        self._base_filename = config.baseFilename
        self._base_directory = config.baseDirectory
        self._centre_freq_hz = centre_frequency_hz
        self._sample_rate_sps = sample_rate_sps
        self._post_milliseconds = config.postTriggerMilliSec
        self._pre_milliseconds = 0  # TODO: config.preTriggerMilliSec

        self._max_total_samples = self._sample_rate_sps * ((self._pre_milliseconds + self._post_milliseconds) / 1000)
        self._number_samples_written = 0
        self._triggered = False
        self._file = None
        self._start_time = 0

        self._complex_post_data = None
        self._post_index = 0
        self._complex_pre_data = None

    def _start(self) -> None:
        """
        Open a temporary file so that we can set the time as part of the filename when we close it

        :return: None
        """
        try:
            self._file = tempfile.TemporaryFile(delete=False)  # as we will rename it at the end
            self._start_time = time.time() - (self._pre_milliseconds / 1000)
            self._triggered = True

            # self._complex_post_data = np.array(shape=(self._max_total_samples,), dtype=np.complex64)
            # self._post_index = 0

            print("Snap started")
            logger.info("Snap started")
        except OSError as e:
            logger.error(e)
            self._file = None

    def _end(self) -> None:
        """
        Close the file
        """
        if self._file:
            self._file.close()  # would of normally delete the temporary file, but we added delete=False

            # create the filename we will use
            then = int(self._start_time)
            filename = self._base_filename + f".{then}.cf{self._centre_freq_hz / 1e6:.6f}" \
                                             f".cplx.{self._sample_rate_sps:.0f}.16tle"
            path_and_filename = f"{self._base_directory}\\{filename}"

            seconds = self._number_samples_written / self._sample_rate_sps
            print(f"Record: {path_and_filename}  {seconds}s {self._number_samples_written} samples")
            logger.info(f"Record: {path_and_filename}  {seconds}s {self._number_samples_written} samples")

            os.renames(self._file.name, path_and_filename)
            self._file = None

    def write(self, trigger: bool, data: np.array) -> bool:
        """
        Write the data to the file

        :param trigger: Boolean that indicates we have to start writing to file
        :param data: To write, complex floating point values
        :return: None
        """
        end = False

        if not self._triggered:
            if trigger:
                self._start()

        if self._file:
            if (self._max_total_samples - self._number_samples_written) > 0:
                # this is messy as we wish to write out 16tle and we have floating point complex samples
                converted_data = np.empty(shape=(1, 2 * data.size), dtype="int16")[0]
                index_out = 0
                data *= 32768  # scale to max of int16 type, as we know we are already limited to +-1 on inputs
                for val in data:
                    converted_data[index_out] = np.int16(val.real)
                    converted_data[index_out + 1] = np.int16(val.imag)
                    index_out += 2

                _ = converted_data.tofile(self._file)

                self._number_samples_written += data.shape[0]
                if (self._max_total_samples - self._number_samples_written) <= 0:
                    self._end()
                    end = True

        return end