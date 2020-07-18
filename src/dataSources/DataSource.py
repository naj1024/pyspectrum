import logging

import numpy as np

# We may need to import the required support, but this may fail.
# But as our source is imported at run time AND when imported by the factory then we will attempt to
# import twice, and may fail twice. So we need a way of giving some type of error message to the user,
# but not twice. Setting an error string is one way and then calling is_available() to find out
import_error_msg = ""

logger = logging.getLogger('spectrum_logger')

supported_data_types = ["8t", "8o", "16tbe", "16tle"]


class DataSource:
    """
    Base class for all the DataSource classes

    Inherit from this and the with a correct module name (e.g. DataSource_xyz) the factory should pick it up

    The main method you have to implement in a new source is:
        def read_cplx_samples(self) -> Tuple[np.array, float]:
            Get complex float samples from the device
            :return: A tuple of a numpy array of complex samples (dtype=complex64) and time in nsec
    """

    def __init__(self,
                 source: str,
                 number_complex_samples: int,
                 data_type: str,
                 sample_rate: float,
                 centre_frequency: float):
        """
        A wrapper around different types of data source that we may wish to have

        TODO: Add more sample types

        :param source: This source name is meaningful to the DataSource only
        :param number_complex_samples: How many samples we expect to get each time
        :param data_type: The type of data that this source will be converting to complex floats/doubles
        :param sample_rate: The sample rate this source is supposed to be working at, in Hz
        :param centre_frequency: The centre frequency this input is supposed to be at, in Hz

        """
        self._source = source
        self._display_name = source
        self._number_complex_samples = number_complex_samples
        self._data_type = data_type
        self._sample_rate = sample_rate
        self._centre_frequency = centre_frequency

        self._bytes_per_snap = 0  # used for input sources that need to know bytes per sample
        self.set_sample_type(data_type)

        self._connected = False

    def close(self) -> None:
        pass

    def connected(self) -> bool:
        """
        Are we connected to the source

        :return: boolean
        """
        return self._connected

    def connect(self) -> bool:
        # Override in derived class if required
        return self._connected

    def reconnect(self) -> bool:
        # Override in derived class if required
        return self._connected

    def get_display_name(self):
        return self._display_name

    def get_sample_rate(self):
        return self._sample_rate

    def get_sample_type(self):
        return self._data_type

    def set_sample_type(self, data_type: str):
        """
        Configure how many bytes per sample we expect

        :param data_type: The type of samples we expect to handle
        :return: None
        """
        # how many bytes are required if reading bytes from somewhere
        # side effect is that we check for the types we can handle
        if data_type == '16tle':
            self._bytes_per_snap = self._number_complex_samples * 4
        elif data_type == '16tbe':
            self._bytes_per_snap = self._number_complex_samples * 4
        elif data_type == '8t':
            self._bytes_per_snap = self._number_complex_samples * 2
        elif data_type == '8o':
            self._bytes_per_snap = self._number_complex_samples * 2
        else:
            msgs = f'Unsupported data type {self._data_type}'
            logger.error(msgs)
            raise ValueError(msgs)
        self._data_type = data_type

    def get_bytes_per_sample(self):
        return self._bytes_per_snap // self._number_complex_samples

    def get_centre_frequency(self):
        return self._centre_frequency

    def unpack_data(self, data: bytes) -> np.ndarray:
        """ Method convert bytes into floats using the specified data type

        When there are more bytes than can be converted to pairs of samples then the excess
        is ignored silently.

        pyrtlsdr uses ctypes for what looks like 8o, it is fast

        Note 8t,16tbe,16tle samples will be scaled to +-1.0,

        :param data: The data bytes to convert
        :return: complex floats in a numpy array
        """
        # put data back into +-1 range as a complex 32bit float
        if self._data_type == '16tle':
            # little endian short signed int
            num_samples = len(data) // 2  # 2 bytes per number
            # use a numpy array for speed, DO NOT use struct.unpack()
            # unpack as shorts into ints
            data_ints = np.ndarray(np.shape(1), dtype=f'<{num_samples}h', buffer=data)
            # convert to floats +-1.0
            data_floats = data_ints / 32767.5
            # create complex, I,Q,I,Q interleaved in floats
            complex_data = np.array(data_floats[0::2], dtype=np.complex64)
            complex_data.imag = data_floats[1::2]

        elif self._data_type == '16tbe':
            # big endian short signed int
            num_samples = len(data) // 2  # 2 bytes per number
            data_ints = np.ndarray(np.shape(1), dtype=f'>{num_samples}h', buffer=data)
            data_floats = data_ints / 32767.5
            complex_data = np.array(data_floats[0::2], dtype=np.complex64)
            complex_data.imag = data_floats[1::2]

        elif self._data_type == '8t':
            # signed 8bit binary, 2s complement
            num_samples = len(data)  # 1 signed byte per inb
            data_ints = np.ndarray(np.shape(1), dtype=f'{num_samples}b', buffer=data)
            data_floats = data_ints / 127.5
            complex_data = np.array(data_floats[0::2], dtype=np.complex64)
            complex_data.imag = data_floats[1::2]

        elif self._data_type == '8o':
            # offset 8bit binary
            num_samples = len(data)  # 1 unsigned byte per int
            # data is offset binary so is unsigned char, convince python to convert it to signed
            data_ints = np.ndarray(np.shape(1), dtype=f'{num_samples}B', buffer=data)
            # could xor top bit
            # data_floats = np.bitwise_xor(data_ints, 128).astype(np.int8) / 127.5
            data_floats = (data_ints - 128).astype(np.int8) / 127.5
            complex_data = np.array(data_floats[0::2], dtype=np.complex64)
            complex_data.imag = data_floats[1::2]

        else:
            err_msg = f'Unsupported data type {self._data_type}'
            logger.error(err_msg)
            raise ValueError(err_msg)

        return complex_data
