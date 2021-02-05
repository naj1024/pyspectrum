"""
For saving samples to file

We save the raw float data to file:
    * converting to 16bit ints takes to long
    * we don't write buffers immediately so that we won't stall the input samples
    * if we are triggered before we have accumulated sufficient pre-trigger samples we just go with what we have

"""
import datetime
import logging
import pathlib
import wave

import numpy as np

from misc import SnapVariables

logger = logging.getLogger('spectrum_logger')


class FileOutput:
    """
    Simple wrapper class for writing binary data to file
    """

    def __init__(self, config: SnapVariables):
        """
        Configure the snapshot

        :param config: How the snap is configured
        """
        self._base_filename = config.baseFilename
        self._base_directory = config.baseDirectory
        self._centre_freq_hz = config.cf
        self._sample_rate_sps = config.sps
        self._post_milliseconds = config.postTriggerMilliSec
        self._pre_milliseconds = config.preTriggerMilliSec
        max_file_size = config.max_file_size
        self._wav_flag = False
        if self._wav_flag == "On":
            self._wav_flag = True

        self._max_total_samples = self._sample_rate_sps * ((self._pre_milliseconds + self._post_milliseconds) / 1000)

        # check we don't go over the max file size we are allowing, 8bytes per IQ sample for float32 * 2
        if (self._max_total_samples * 8) > max_file_size:
            self._max_total_samples = max_file_size / 8
            secs = self._max_total_samples / self._sample_rate_sps
            self._post_milliseconds = secs * 1000
            self._pre_milliseconds = 0  # curtail all pre-trigger samples
            logger.error(f"Max file size of {max_file_size}MBytes exceeded, limiting to post {secs}seconds")

        self._number_samples_written = 0

        self._complex_post_data = []
        self._post_data_samples = 0
        self._required_post_data_samples = (self._post_milliseconds / 1000) * self._sample_rate_sps

        self._complex_pre_data = []
        self._pre_data_samples = 0
        self._required_pre_data_samples = (self._pre_milliseconds / 1000) * self._sample_rate_sps

        self._triggered = False
        self._file = None
        self._start_time_nsec = 0

    def __del__(self):
        if self._triggered:
            self._end()

    def get_pre_trigger_milli_seconds(self) -> float:
        return self._pre_milliseconds

    def get_post_trigger_milli_seconds(self) -> float:
        return self._post_milliseconds

    def get_current_size_mbytes(self) -> float:
        # 8bytes per sample
        return (8*(self._post_data_samples + self._pre_data_samples)) / (1024*1024)

    def get_size_mbytes(self) -> float:
        return (8 * self._max_total_samples) / (1024 * 1024)

    def _start(self, time_rx_nsec: float) -> None:
        """
        initialise the start

        :param time_rx_nsec: the time we wish to use as the start time
        :return: None
        """
        try:
            secs_pre = self._pre_data_samples / self._sample_rate_sps
            self._start_time_nsec = time_rx_nsec - secs_pre * 1e9
            self._triggered = True

            self._complex_post_data = []
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
            fract_sec = (self._start_time_nsec / 1e9) - then
            date_time = datetime.datetime.utcfromtimestamp(then).strftime('%Y-%m-%d_%H-%M-%S')
            fract_sec = str(round(fract_sec, 3)).lstrip('0')
            filename = self._base_filename + f".{date_time}{fract_sec}" \
                                             f".cf{self._centre_freq_hz / 1e6:.6f}" \
                                             f".cplx.{self._sample_rate_sps:.0f}.32fle"

            if self._wav_flag:
                filename += ".wav"

            path_and_filename = pathlib.PurePath(self._base_directory + "/" + filename)

            try:
                if self._wav_flag:
                    file = wave.open(str(path_and_filename), "wb")
                    file.setframerate(self._sample_rate_sps)
                    file.setnchannels(2)  # iq
                    file.setsampwidth(4)  # 32bit floats
                    # the wav module has no support for changing the format to float32
                    for buff in self._complex_pre_data:
                        file.writeframes(buff)
                    for buff in self._complex_post_data:
                        file.writeframes(buff)
                else:
                    file = open(path_and_filename, "wb")

                    for buff in self._complex_pre_data:
                        file.write(buff)
                    for buff in self._complex_post_data:
                        file.write(buff)

                file.close()

                written = self._post_data_samples + self._pre_data_samples
                seconds = written / self._sample_rate_sps
                msg = f"Record: {path_and_filename} {round(seconds, 6)}s, {written} samples"
                logger.info(msg)

                # reset, Use post samples to fill pre for another trigger event
                # extra pre samples will get dropped on depth check
                if self._required_pre_data_samples > 0:
                    self._complex_pre_data = self._complex_post_data
                    self._pre_data_samples = self._post_data_samples
                else:
                    self._complex_pre_data = []
                    self._pre_data_samples = 0
                self._complex_post_data = []
                self._post_data_samples = 0
                self._triggered = False

            except OSError as e:
                logger.error(f"failed to write snapshot to file, {e}")
            except wave.Error as e:
                logger.error(f"failed to write snapshot to wav file, {e}")

            self._complex_post_data = []

    def _limit_pre_samples(self) -> None:
        """
        keep the number of samples pre-trigger to the required number (slightly more due to blocks)
        :return: None
        """
        while self._pre_data_samples > self._required_pre_data_samples:
            self._pre_data_samples -= self._complex_pre_data[0].shape[0]
            del self._complex_pre_data[0]

    def write(self, trigger: bool, data: np.array, time_rx_nsec: float) -> bool:
        """
        Write the data for the snapshot.
        Keep a record of samples we will write to file at the end

        :param trigger: Boolean that indicates we have to start writing to file
        :param data: To write, complex floating point values
        :param time_rx_nsec: time of this data block
        :return: None
        """
        end = False

        if not self._triggered:
            if trigger:
                self._start(time_rx_nsec)  # sets self._triggered
            else:
                # add to pre-trigger samples
                if self._pre_milliseconds > 0:
                    copied = np.array(data)
                    self._pre_data_samples += data.shape[0]
                    self._complex_pre_data.append(copied)
                    self._limit_pre_samples()

        if self._triggered:
            if (self._required_post_data_samples - self._post_data_samples) >= 0:
                copied = np.array(data)
                self._complex_post_data.append(copied)
                self._post_data_samples += data.shape[0]

            # are we finished, may not have sufficient pre-samples but can't do much about that
            if (self._required_post_data_samples - self._post_data_samples) <= 0:
                self._end()
                end = True

        return end
