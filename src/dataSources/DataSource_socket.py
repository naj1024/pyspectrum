import socket
from typing import Tuple
import logging

import numpy as np

from dataSources import DataSource

module_type = "socket"
help_string = f"{module_type}:IP:port \t- The Ip or resolvable name and port of a server, " \
              f"e.g. {module_type}:192.168.2.1:12345"
web_help_string = "IP:port - The Ip or resolvable name and port of a server, e.g. 192.168.2.1:12345"

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
                 data_type: str,
                 sample_rate: float,
                 centre_frequency: float,
                 input_bw: float):
        """Initialise the object
        Args:
        :param ip_address_port: The address and port we connect to, address empty then we are the server
        :param data_type: The type of data we are going to be receiving on the socket
        :param sample_rate: The sample rate this source is supposed to be working at, in Hz
        :param centre_frequency: The centre frequency this input is supposed to be at, in Hz
        :param input_bw: The filtering of the input, may not be configurable
        """

        super().__init__(ip_address_port, data_type, sample_rate, centre_frequency, input_bw)
        self._connected = False
        self._ip_address = ""  # filled in when we open()
        self._ip_port = 0  # filled in when we open()
        self._socket = None
        self._served_connection = None
        self._client = True
        super().set_help(help_string)
        super().set_web_help(web_help_string)

    def open(self) -> bool:
        # specifics to this class
        # break apart the ip address and port, will be something like 192.168.0.1:1234

        if self._source == "?":
            self._error = f"Can't scan for {module_type} devices"
            return False

        parts = self._source.split(':')
        if len(parts) < 2:
            raise ValueError(f"input specification does not contain two colon separated items, "
                             f"{self._source}")
        self._ip_address = parts[0]
        try:
            self._ip_port = int(parts[1])
        except ValueError as msg:
            msgs = f"port number from {parts[1]}, {msg}"
            self._error = str(msgs)
            logger.error(msgs)
            raise ValueError(msgs)

        if self._ip_port < 0:
            msgs = f"port number from {parts[1]} is negative"
            self._error = msgs
            logger.error(msgs)
            raise ValueError(msgs)

        self._client = True
        if self._ip_address == "":
            self._client = False

        self.connect()

        return self._connected

    def close(self) -> None:
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
        except Exception as msg:
            logger.error(msg)
            raise ValueError(msg)

        return self._connected

    def is_server(self) -> bool:
        return not self._client

    def read_cplx_samples(self, number_samples: int) -> Tuple[np.array, float]:
        """Read data from the socket and convert them to complex floats using the data type specified

        :return: A tuple of a numpy array of complex samples and time in nsec
        """
        complex_data = None
        rx_time = 0

        if self._connected:
            total_bytes = self._bytes_per_complex_sample * number_samples
            raw_bytes = bytearray()
            try:
                sock = None
                if self._client:
                    sock = self._socket
                else:
                    sock = self._served_connection

                if sock:
                    while sock and (len(raw_bytes) != total_bytes):
                        got: bytearray = sock.recv(total_bytes)  # will get a MAXIMUM of this number of bytes
                        if rx_time == 0:
                            rx_time = self.get_time_ns()
                        if len(got) == 0:
                            self.close()
                            logger.info('Socket connection closed')
                            raise ValueError('Socket connection closed')
                        raw_bytes += got
                        total_bytes -= len(got)

            except OSError as msg:
                self.close()
                msgs = f'OSError, {msg}'
                self._error = str(msgs)
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

            if len(raw_bytes) == total_bytes:
                complex_data = self.unpack_data(raw_bytes)
            else:
                complex_data = np.empty(0)
                logger.error(f'Socket gave incorrect # of bytes, got {len(raw_bytes)} expected {total_bytes}')

        return complex_data, rx_time
