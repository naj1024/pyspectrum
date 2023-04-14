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

import numpy as np

from misc import Snapper
from misc import wave_b as wave

logger = logging.getLogger('spectrum_logger')

try:
    import_error_msg = ""
    import sigmf
    from sigmf import SigMFFile
    from sigmf.utils import get_data_type_str
except ImportError as msg:
    sigmf = None
    SigMFFile = None
    get_data_type_str = None
    import_error_msg = f"{__name__} has an no sigmf support: {str(msg)}"
    logging.error(import_error_msg)


class FileOutput:
    """
    Simple wrapper class for writing binary data to file
    """

    def __init__(self, config: Snapper, snap_dir: pathlib.PurePath):
        """
        Configure the snapshot

        :param config: How the snap is configured
        :param snap_dir: where the snaps go
        """
        self._base_filename = config.baseFilename
        if len(self._base_filename) == 0:
            self._base_filename = "snap"
            config.baseFilename = self._base_filename
        self._base_directory = snap_dir
        self._centre_freq_hz = config.cf
        self._sample_rate_sps = config.sps
        self._post_milliseconds = config.postTriggerMilliSec
        self._pre_milliseconds = config.preTriggerMilliSec
        max_file_size = config.max_file_size

        self._wav_flag = False
        self._sigmf_flag = False
        if config.file_format == "wav":
            self._wav_flag = True
        elif config.file_format == "sigmf":
            self._sigmf_flag = True

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
            self._write_to_file()

    def get_base_filename(self) -> str:
        return self._base_filename

    def get_base_directory(self) -> pathlib.PurePath:
        return self._base_directory

    def get_centre_frequency(self) -> int:
        return self._centre_freq_hz

    def get_smaple_rate(self) -> int:
        return self._sample_rate_sps

    def get_pre_trigger_milli_seconds(self) -> float:
        return self._pre_milliseconds

    def get_post_trigger_milli_seconds(self) -> float:
        return self._post_milliseconds

    def get_current_size_mbytes(self) -> float:
        # 8bytes per sample
        return (8 * (self._post_data_samples + self._pre_data_samples)) / (1024 * 1024)

    def get_size_mbytes(self) -> float:
        return (8 * self._max_total_samples) / (1024 * 1024)

    def get_sps(self) -> float:
        return self._sample_rate_sps

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

    def _filename(self, sigmf_type: str = 'data') -> str:
        then = int(self._start_time_nsec / 1e9)
        fractional_sec = (self._start_time_nsec / 1e9) - then
        date_time = datetime.datetime.utcfromtimestamp(then).strftime('%Y-%m-%d_%H-%M-%S')
        fractional_sec = str(round(fractional_sec, 3)).lstrip('0')
        filename = self._base_filename + f".{date_time}{fractional_sec}" \
                                         f".cf{self._centre_freq_hz / 1e6:.6f}" \
                                         f".cplx.{self._sample_rate_sps:.0f}"
        if self._wav_flag:
            filename += ".wav"
        elif self._sigmf_flag:
            filename += f".sigmf-{sigmf_type}"  # surely this should be type-sigmf to allow easier parsing
        else:
            filename += ".32fle"

        return filename

    def _write_wav(self, path: pathlib.PurePath):
        try:
            file = wave.open(str(path), "wb")
            file.setframerate(self._sample_rate_sps)
            file.setnchannels(2)  # iq
            file.setsampwidth(4)  # 32bit floats
            file.setwformat(wave.WAVE_FORMAT_IEEE_FLOAT)
            # the wav module has no support for changing the format to float32
            # we will write complex float32 and the wave file will be set to int32
            for buff in self._complex_pre_data:
                file.writeframes(buff)
            for buff in self._complex_post_data:
                file.writeframes(buff)
            file.close()
        except OSError as e:
            err = f"failed to write wav snapshot to file, {e}"
            raise ValueError(err)
        except wave.Error as e:
            err = f"failed to write snapshot to wav file, {e}"
            raise ValueError(err)

    def _write_sgmf_meta(self):
        # meta data is in separate file
        meta_filename = self._filename('meta')
        path_and_meta_filename = pathlib.PurePath(self._base_directory, meta_filename)

        # create the metadata
        meta = SigMFFile(
            # don't use data_file, as we have a compliant data filename and OS can't find it without the path
            # data_file = ,
            # no paths allowed, so no leak of your environment
            global_info={
                SigMFFile.DATATYPE_KEY: get_data_type_str(self._complex_pre_data[0]),  # in this case, 'cf32_le' ??
                SigMFFile.SAMPLE_RATE_KEY: self._sample_rate_sps,
                SigMFFile.DESCRIPTION_KEY: 'SDR samples.',
                SigMFFile.VERSION_KEY: sigmf.__version__,
                SigMFFile.RECORDER_KEY: 'pyspectrum'
            }
        )

        seconds, microseconds = divmod(self._start_time_nsec, 1000000000)
        dt = datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc) + datetime.timedelta(
            microseconds=microseconds)

        # create a capture key at time index 0
        meta.add_capture(0, metadata={
            SigMFFile.FREQUENCY_KEY: self._centre_freq_hz,
            SigMFFile.DATETIME_KEY: dt.isoformat(sep='T', timespec='microseconds') + 'Z',
        })

        # check for mistakes & write to disk
        meta.tofile(str(path_and_meta_filename))

    def _write_to_file(self) -> None:
        """
        Write out the data to file

        """
        if len(self._complex_post_data):
            filename = self._filename()

            try:
                path_and_filename = pathlib.PurePath(self._base_directory, filename)

                if self._wav_flag:
                    self._write_wav(path_and_filename)
                else:
                    # straight binary data of complex 32f
                    file = open(path_and_filename, "wb")
                    for buff in self._complex_pre_data:
                        file.write(buff)
                    for buff in self._complex_post_data:
                        file.write(buff)
                    file.close()

                    # may have to write the metadata to a separate file
                    # do this before we delete the buffers
                    if self._sigmf_flag:
                        self._write_sgmf_meta()

                written = self._post_data_samples + self._pre_data_samples
                seconds = written / self._sample_rate_sps
                msg = f"Record: {path_and_filename} {round(seconds, 6)}s, {written} samples"
                logger.info(msg)

                # reset
                # Start again otherwise you will end up with samples being duplicated between quick triggers
                self._complex_pre_data = []
                self._pre_data_samples = 0
                self._complex_post_data = []
                self._post_data_samples = 0
                self._triggered = False

            except OSError as e:
                logger.error(f"failed to write snapshot to file, {e}")
            except wave.Error as e:
                logger.error(f"failed to write snapshot to wav file, {e}")
            except ValueError as e:
                logger.error(e)

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
                self._write_to_file()
                end = True

        return end
