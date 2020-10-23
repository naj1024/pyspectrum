import socket
from typing import Tuple
import logging
import time

import numpy as np

from dataSources import DataSource

module_type = "socket"
help_string = f"{module_type}:IP@port \t- The Ip or resolvable name and port of a server, " \
              f"e.g. {module_type}:192.168.2.1@12345"

logger = logging.getLogger('spectrum_logger')


# return an error string if we are not available
def is_available() -> Tuple[str, str]:
    return module_type, ""


class Input(DataSource.DataSource):
    """ A class that will be used to service a socket, client or server

     Provides numpy arrays of complex float samples
     """

    def __init__(self,
                 ip_address_port: str,
                 number_complex_samples: int,
                 data_type: str,
                 sample_rate: float,
                 centre_frequency: float):
        """Initialise the object
        Args:
        :param ip_address_port: The address and port we connect to, address empty then we are the server
        :param number_complex_samples: The number of complex samples we expect to get every call to read_cplx_samples()
        :param data_type: The type of data we are going to be receiving on the socket
        :param sample_rate: The sample rate this source is supposed to be working at, in Hz
        :param centre_frequency: The centre frequency this input is supposed to be at, in Hz
        """

        super().__init__(ip_address_port, number_complex_samples, data_type, sample_rate, centre_frequency)

        # specifics to this class
        # break apart the ip address and port, will be something like 192.168.0.1@1234

        parts = ip_address_port.split('@')
        if len(parts) != 2:
            raise ValueError(f"{module_type} input specification does not contain two colon separated items, "
                             f"{ip_address_port}")
        self._ip_address = parts[0]
        try:
            self._ip_port = int(parts[1])
        except ValueError as msg:
            msgs = f"{module_type} port number from {parts[1]}, {msg}"
            logger.error(msgs)
            raise ValueError(msgs)

        if self._ip_port < 0:
            msgs = f"{module_type} port number from {parts[1]} is negative"
            logger.error(msgs)
            raise ValueError(msgs)

        self._socket = None
        self._served_connection = None

        self._client = True
        if self._ip_address == "":
            self._client = False

    def is_server(self) -> bool:
        return not self._client

    def reconnect(self) -> bool:
        """
        Reconnect using the previous connect settings

        We will return either connected or an exception. The caller can then decide what to do, i.e.
        maybe a ctrl-c event has to be handled to terminate the programme
        :return: Boolean on success/failure
        """
        logger.debug(f"Reconnecting to socket {self._ip_address} port {self._ip_port}")
        time.sleep(1)  # we may get called a lot on not connected, so slow reconnects down a bit
        self._connected = False
        self._connected = self.connect()
        return self._connected

    def close(self):
        if self._client:
            sock = self._socket
        else:
            sock = self._served_connection
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
                sock.close()
            except OSError as msg:
                logger.info(f"Problem on socket shutdown/close, {msg}")
        self._socket = None
        self._served_connection = None
        self._connected = False

    def connect(self) -> bool:
        """Provide a socket connection

        We will return either connected or an exception. The caller can then decide what to do, i.e.
        maybe a ctrl-c event has to be handled to terminate the programme

        Returns:
            The connection state, True if we connected to a server or have a client connected to us
        """
        self._connected = False
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if self._client:
                # we have an IP address to connect to so we are a client
                self._socket.connect((self._ip_address, self._ip_port))
                self._connected = True
                logger.debug(f"Connected to socket {self._ip_address} on port {self._ip_port}")
            else:
                logger.debug(f"Listening on port {self._ip_port}")
                self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._socket.bind((self._ip_address, self._ip_port))
                self._socket.listen()
                self._served_connection, _ = self._socket.accept()
                self._served_connection.setblocking(True)
                self._connected = True
                logger.debug(f"Connection from {self._served_connection.getpeername()}")
        except Exception:
            raise

        return self._connected

    def read_cplx_samples(self) -> Tuple[np.array, float]:
        """Read data from the socket and convert them to complex floats using the data type specified

        :return: A tuple of a numpy array of complex samples and time in nsec
        """
        sock = None
        rx_time = 0
        raw_bytes = bytearray()
        try:
            if self._client:
                sock = self._socket
            else:
                sock = self._served_connection

            if sock:
                num_bytes_to_get = self._bytes_per_snap
                while sock and (len(raw_bytes) != self._bytes_per_snap):
                    got: bytearray = sock.recv(num_bytes_to_get)  # will get a MAXIMUM of this number of bytes
                    if rx_time == 0:
                        rx_time = self.get_time_ns()
                    if len(got) == 0:
                        self.close()
                        logger.info('Socket connection closed')
                        raise ValueError('Socket connection closed')
                    raw_bytes += got
                    num_bytes_to_get -= len(got)

        except OSError as msg:
            self.close()
            msgs = f'OSError, {msg}'
            logger.error(msgs)
            raise ValueError(msgs)

        # Timing how long conversion takes
        # t1 = time.perf_counter()
        # for w in range(10000):
        #     if len(raw_bytes) == self._number_bytes:
        #         complex_data = self.unpack_data(raw_bytes)
        #     else:
        #         complex_data = np.empty(0)
        #         print(
        #             f'Error: Socket gave incorrect # of bytes, got {len(raw_bytes)} '
        #             f'expected {self._number_bytes}')
        # t2 = time.perf_counter()
        # print(f"{1000000.0 * (t2 - t1) / 10000.0}usec")

        if len(raw_bytes) == self._bytes_per_snap:
            complex_data = self.unpack_data(raw_bytes)
        else:
            complex_data = np.empty(0)
            logger.error(f'Socket gave incorrect # of bytes, got {len(raw_bytes)} expected {self._bytes_per_snap}')

        return complex_data, rx_time
