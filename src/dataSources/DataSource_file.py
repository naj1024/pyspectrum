"""
File input class

"""
import time
import logging
from typing import Tuple

import numpy as np

from dataSources import DataSource
from misc import FileOpen

logger = logging.getLogger('spectrum_logger')

module_type = "file"
help_string = f"{module_type}:Filename \t- Filename, binary or wave, e.g. " \
              f"{module_type}:./xyz.cf123.4.cplx.200000.16tbe"
web_help_string = "Filename - Filename, binary or wave, e.g. ./xyz.cf123.4.cplx.200000.16tbe"


# return an error string if we are not available
def is_available() -> Tuple[str, str]:
    return module_type, ""


class Input(DataSource.DataSource):

    def __init__(self,
                 file_name: str,
                 number_complex_samples: int,
                 data_type: str,
                 sample_rate: float,
                 centre_frequency: float,
                 input_bw: float):
        """
        File input class

        :param file_name: File name including path if required
        :param number_complex_samples: How many complex samples we require on each read
        :param data_type: The type of data we have in the file
        :param sample_rate: The sample rate this source is supposed to be working at, in Hz
        :param centre_frequency: The centre frequency this input is supposed to be at, in Hz
        :param input_bw: The filtering of the input, may not be configurable
        """
        self._is_wav_file = False  # until we work it out

        super().__init__(file_name, number_complex_samples, data_type, sample_rate, centre_frequency, input_bw)

        self._file = None
        self._rewind = True  # true if we will rewind the file each time it ends
        self._connected = False

        try:
            self._create_time = time.time_ns()
        except AttributeError:
            self._create_time = time.time()

        self._file_time = self._create_time  # for timing the samples from the file, increment according to sample rate
        super().set_help(help_string)
        super().set_web_help(web_help_string)

    def __del__(self):
        if self._file:
            self._file.close()

    def open(self) -> bool:
        try:
            file = FileOpen.FileOpen(self._source)
            ok, self._file, self._is_wav_file, data_type, sps, cf = file.open()
            # only update the following if we managed to recover them on the open()
            if ok:
                self.set_sample_type(data_type)
                self._centre_frequency_hz = cf
                self._sample_rate_sps = sps

        except ValueError as msg:
            self._error = msg
            logger.error(msg)
            raise ValueError(msg)

        self._connected = True
        return self._connected

    def set_rewind(self, allow: bool):
        self._rewind = allow

    def close(self) -> None:
        if self._file:
            self._file.close()
        self._file = None
        self._connected = False

    def rewind(self) -> bool:
        """
        Rewind the input file

        :return: Boolean true if we managed to rewind the file
        """
        # Rewind the file
        self._connected = False
        try:
            if self._is_wav_file:
                self._file.rewind()
            else:
                self._file.seek(0, 0)

            # could reset to create_time but time must always increase
            # otherwise the acks coming back will allow huge tcp buffer storage
            # self._file_time = self._create_time  # start again
        except OSError as msg:
            msgs = f'Failed to rewind {self._source}, {msg}'
            self._error = str(msgs)
            logger.error(msgs)
            raise ValueError(msgs)

        self._connected = True
        return self._connected

    def read_cplx_samples(self) -> Tuple[np.array, float]:
        """
        Get complex float samples from the device.
        :return: A tuple of a numpy array of complex samples and time in nsec
        """
        complex_data = None
        rx_time = 0  # in nsec

        if self._connected:
            raw_bytes = None
            if self._file:
                try:
                    if self._is_wav_file:
                        raw_bytes = self._file.readframes(self._number_complex_samples)
                    else:
                        # get just the number of bytes we needs
                        raw_bytes = self._file.read(self._bytes_per_snap)
                    rx_time = self._file_time  # mark start of buffer as current distance into file
                    # update time into the file by the sample rate
                    self._file_time += (1.0e9 * self._number_complex_samples / self._sample_rate_sps)

                    if len(raw_bytes) != self._bytes_per_snap:
                        raw_bytes = None
                        if self._rewind:
                            self.rewind()
                        else:
                            raise ValueError("end-of-file")

                    # wait how long these samples would of taken to arrive, but not too long
                    sleep = self._number_complex_samples / self._sample_rate_sps
                    if sleep < 1.0:
                        time.sleep(sleep)

                except OSError as msg:
                    msgs = f'OSError, {msg}'
                    self._error = str(msgs)
                    logger.error(msgs)
                    raise ValueError(msgs)
                except ValueError as msg:
                    if self._rewind:
                        msgs = f'file exception, {msg}'
                        self._error = str(msgs)
                        logger.error(msgs)
                        raise ValueError(msgs)
                    else:
                        raise ValueError("eof")

            if raw_bytes:
                complex_data = self.unpack_data(raw_bytes)

        return complex_data, rx_time
