"""
For saving samples to file

We save the raw float data to file:
    * converting to 16bit ints takes to long, either we drop samples each buffer or at then end when we write
      all the buffers
    * we don't write buffers immediately so that we won't stall the input samples

TODO: implement the wrap round buffer for pre-trigger samples
TODO: maybe add .wav output type
TODO: maybe have another process that converts samples to 16bit?, or wav
"""
import datetime
import logging
import pathlib

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
        self._pre_milliseconds = 0  # config.preTriggerMilliSec not implemented
        max_file_size = config.max_file_size

        self._max_total_samples = self._sample_rate_sps * ((self._pre_milliseconds + self._post_milliseconds) / 1000)

        # check we don't go over the max file size we are allowing, 8bytes per IQ sample for float32 * 2
        if (self._max_total_samples * 8) > max_file_size:
            self._max_total_samples = max_file_size / 8
            secs = self._max_total_samples / self._sample_rate_sps
            # TODO: handle pre as well
            self._post_milliseconds = secs * 1000
            logger.error(f"Max file size of {max_file_size}MBytes exceeded, limiting to {secs}seconds")

        self._number_samples_written = 0
        self._triggered = False
        self._file = None
        self._start_time_nsec = 0

        self._complex_post_data = []
        self._complex_pre_data = None

    def get_pre_trigger_milli_seconds(self) -> float:
        return self._pre_milliseconds

    def get_post_trigger_milli_seconds(self) -> float:
        return self._post_milliseconds

    def _start(self, time_rx_nsec: float) -> None:
        """
        initialise the start

        :param time_rx_nsec: the time we wish to use as the start time
        :return: None
        """
        try:
            # TODO: account for the pre-trigger, not simple as data comes in blocks
            self._start_time_nsec = time_rx_nsec  # - (self._pre_milliseconds * 1000)
            self._triggered = True

            self._complex_post_data = []
            self._post_index = 0
            logger.info("Snap started")
        except OSError as e:
            logger.error(e)
            self._file = None

    def _end(self) -> None:
        """
        Write out the data to file

        """
        if len(self._complex_post_data):
            then = int(self._start_time_nsec / 1e9)
            date_time = datetime.datetime.utcfromtimestamp(then).strftime('%Y-%m-%d_%H-%M-%S')
            filename = self._base_filename + f".{date_time}.cf{self._centre_freq_hz / 1e6:.6f}" \
                                             f".cplx.{self._sample_rate_sps:.0f}.32fle"
            path_and_filename = pathlib.PurePath(self._base_directory + "/" + filename)

            try:
                file = open(path_and_filename, "wb")
                for buff in self._complex_post_data:
                    file.write(buff)
                file.close()

                seconds = self._number_samples_written / self._sample_rate_sps
                msg = f"Record: {path_and_filename}  {round(seconds, 6)}s {self._number_samples_written} samples"
                logger.info(msg)
            except OSError as e:
                logger.error(f"failed to write snapshot to file, {e}")

            self._complex_post_data = []

    def write(self, trigger: bool, data: np.array, time_rx_nsec: float) -> bool:
        """
        Write the data for the snapshot

        :param trigger: Boolean that indicates we have to start writing to file
        :param data: To write, complex floating point values
        :param time_rx_nsec: time of this data block
        :return: None
        """
        end = False

        if not self._triggered:
            if trigger:
                self._start(time_rx_nsec)

        if self._triggered:
            if (self._max_total_samples - self._number_samples_written) >= 0:
                # take a copy of the data for now
                copied = np.array(data)
                # add it to the list of buffers
                self._complex_post_data.append(copied)
                self._number_samples_written += data.shape[0]

                if (self._max_total_samples - self._number_samples_written) <= 0:
                    self._end()
                    end = True

        return end
