"""
A RTLSDR-TCP wrapper based on a socket connection

This is based on (but without the queue as to benefit properly it should be in a separate process):
     https://gitlab.com/librespacefoundation/satnogs/satnogs-misc/-/tree/master/simple_tcp_receiver

NOTE
====
   The rtl_tcp server code allows unlimited backup if the samples are not read from the socket fast enough.
This is not very wise. if you see ll+/ll- on the server stdout then you are not reading fast enough across the
tcp connection to keep up with the digitisation rate.
   To be safe(r) modify rtl_tcp.c in rtlsdr_callback() to limit the outstanding queue depth to 100 buffers from
the device. Each buffer is 128k complex samples (256k bytes):

    Replace in rtl_tcp.c rtlsdr_callback():
        if(llbuf_num && llbuf_num == num_queued-2){
            struct llist *curelem;

            free(ll_buffers->data);
            curelem = ll_buffers->next;
            free(ll_buffers);
            ll_buffers = curelem;
        }

        cur->next = rpt;

        if (num_queued > global_numq)
            printf("ll+, now %d\n", num_queued);
        else if (num_queued < global_numq)
            printf("ll-, now %d\n", num_queued);

    With:
        // 100 buffers at 3Msps is over 4 seconds
        if(num_queued > 100){
            static int drop_count=0;
            drop_count++;
            printf("Dropping %d samples, %d\n", rpt->len/2, drop_count);
            free(rpt->data);
            free(rpt);
        }
        else{
            cur->next = rpt;
        }

TODO: Put the reader in a separate process and use a multiprocessing queue for the samples + a timestamp
"""

import socket
import struct
import logging
import time
from typing import Tuple

import numpy as np

from dataSources import DataSource

logger = logging.getLogger('spectrum_logger')

module_type = "rtltcp"
help_string = f"{module_type}::IP@port - The Ip or resolvable name and port of an rtltcp server, " \
              f"e.g. {module_type}:192.168.2.1@12345"


# return an error string if we are not available
def is_available() -> Tuple[str, str]:
    return module_type, ""


class Input(DataSource.DataSource):

    def __init__(self,
                 source: str,
                 number_complex_samples: int,
                 data_type: str,
                 sample_rate: float,
                 centre_frequency: float):
        """
        The rtltcp input source

        :param source: Ip and port as a string, e.g. 127.0.0.1@3456
        :param number_complex_samples: The number of complex samples we require each request
        :param data_type: ignored, we will be getting 8bit offset binary, '8o'
        :param sample_rate: The sample rate we will set the source to, note true sps is set from the device
        :param centre_frequency: The centre frequency the source will be set to
        """
        super().__init__(source, number_complex_samples, '8o', sample_rate, centre_frequency)

        # specifics to this class
        # break apart the ip address and port, will be something like 192.168.0.1@1234

        parts = source.split('@')
        if len(parts) != 2:
            raise ValueError(f"{module_type} input specification does not contain two colon separated items, "
                             f"{source}")
        self._ip_address = parts[0]
        try:
            self._ip_port = int(parts[1])
        except ValueError as msg1:
            msgs = f"{module_type} port number from {parts[1]}, {msg1}"
            logger.error(msgs)
            raise ValueError(msgs)

        if self._ip_port < 0:
            msgs = f"{module_type} port number from {parts[1]} is negative"
            logger.error(msgs)
            raise ValueError(msgs)

        self._socket = None
        self._connected = False

    def reconnect(self) -> bool:
        """
        Reconnect using the previous connect settings

        We will return either connected or an exception. The caller can then decide what to do, i.e.
        maybe a ctrl-c event has to be handled to terminate the programme
        :return: Boolean on success/failure
        """
        logger.debug(f"Reconnecting to rtltcp {self._ip_address} port {self._ip_port}")
        time.sleep(1)  # we may get called a lot on not connected, so slow reconnects down a bit
        self._connected = False
        self._connected = self.connect()
        return self._connected

    def connect(self) -> bool:
        """
        We will return either connected or an exception. The caller can then decide what to do, i.e.
        maybe a ctrl-c event has to be handled to terminate the programme

        Returns:
            The connection state, True if we connected to a server
        """
        self._connected = False
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # we have an IP address to connect to so we are a client
            self._socket.connect((self._ip_address, self._ip_port))
            self._connected = True
            logger.debug(f"Connected to rtltcp {self._ip_address} on port {self._ip_port}")

            # say what we want
            self.set_sample_rate(int(self._sample_rate))
            self.set_center_frequency(int(self._centre_frequency))
            # not found a description of gain_mode / agc_mode ...
            self.set_tuner_gain_mode(1)
            # TODO: what's the difference between set_tuner_gain_by_index() and set_tuner_gain() ?
            self.set_tuner_gain_by_index(17)  # ignored unless set_tuner_gain_mode is 1
            self.set_agc_mode(0)
        except Exception:
            raise

        return self._connected

    def read_cplx_samples(self) -> Tuple[np.array, float]:
        """
        Return complex float samples from the device

        :return: A tuple of a numpy array of complex samples and time in nsec
        """
        if not self._connected:
            raise ValueError

        rx_time = 0
        try:
            num_bytes_to_get = self._bytes_per_snap
            raw_bytes = bytearray()
            while len(raw_bytes) != self._bytes_per_snap:
                got: bytearray = self._socket.recv(num_bytes_to_get)  # will get a MAXIMUM of this number of bytes
                if rx_time == 0:
                    rx_time = time.time_ns()
                if len(got) == 0:
                    self._socket.close()
                    self._connected = False
                    logger.info('rtltcp connection closed')
                    raise ValueError('rtltcp connection closed')
                raw_bytes += got
                num_bytes_to_get -= len(got)

        except OSError as msg1:
            if self._socket:
                self._socket.close()
            msgs = f'OSError, {msg1}'
            logger.error(msgs)
            self._connected = False
            raise ValueError(msgs)

        if len(raw_bytes) == self._bytes_per_snap:
            zeros = 0
            for i in range(len(raw_bytes)):
                if raw_bytes[i] == 128:
                    zeros += 1
            if zeros >= (len(raw_bytes) // 2):
                print("zeros")
            complex_data = self.unpack_data(raw_bytes)
        else:
            complex_data = np.empty(0)
            logger.error(f'rtltcp gave incorrect # of bytes, got {len(raw_bytes)} expected {self._bytes_per_snap}')

        return complex_data, rx_time

    ##################################
    #
    # RTL-TCP specifics below here
    # Definitive description seems to be the source code: https://github.com/osmocom/rtl-sdr rtl_tcp.c
    #
    ######################
    def send_command(self, command: int, value: int) -> int:
        """
        pack in network order of unsigned byte followed by unsigned int

        :param command: command byte
        :param value: command value
        :return:  Number of bytes sent
        """
        command = struct.pack('!BI', command & 0xff, value)  # command:bytes
        return self._socket.sendall(command)

    def set_center_frequency(self, value: int) -> int:
        # limits depend on tuner type: from https://wiki.radioreference.com/index.php/RTL-SDR
        # Tuner 	             Frequency Range
        # =======================================
        # Elonics E4000 	     52 – 1100 MHz / 1250 - 2200 MHz
        # Rafael Micro R820T(2)  24 – 1766 MHz
        # Fitipower FC0013 	     22 – 1100 MHz
        # Fitipower FC0012 	     22 - 948.6 MHz
        # FCI FC2580 	         146 – 308 MHz / 438 – 924 MHz

        # We can't see what type is plugged in, default to R820T ranges
        if (value <= 22e6) or (value > 1.766e9):
            err = f"{module_type} invalid centre frequency, {value}Hz"
            logger.error(err)
            value = int(433.92e6)
        logger.info(f"Set frequency {value / 1e6:0.6f}MHz")
        self._centre_frequency = value
        return self.send_command(0x01, value)

    def set_sample_rate(self, value: int) -> int:
        # rtlsdr has limits on allowed sample rates
        # from librtlsdr.c data_source.get_bytes_per_sample()
        # 	/* check if the rate is supported by the resampler */
        # 	if ((samp_rate <= 225000) || (samp_rate > 3200000) ||
        # 	   ((samp_rate > 300000) && (samp_rate <= 900000))) {
        # 		fprintf(stderr, "Invalid sample rate: %u Hz\n", samp_rate);
        # 		return -EINVAL;
        # 	}
        # We have no way of knowing if a command completes on the remote platform
        if (value <= 225000) or (value > 3200000) or ((value > 300000) and (value <= 900000)):
            err = f"{module_type} invalid sample rate, {value}sps"
            logger.error(err)
            value = int(1e6)
        self._sample_rate = value
        logger.info(f"Set sample rate {value}sps")
        return self.send_command(0x02, value)

    def set_tuner_gain_mode(self, value: int) -> int:
        return self.send_command(0x03, value)

    def set_tuner_gain(self, value: int) -> int:
        return self.send_command(0x04, value)

    def set_freq_correction(self, value: int) -> int:
        return self.send_command(0x05, value)

    def set_tuner_if_gain(self, value: int) -> int:
        return self.send_command(0x06, value)

    def set_test_mode(self, value: int) -> int:
        return self.send_command(0x07, value)

    def set_agc_mode(self, value: int) -> int:
        return self.send_command(0x08, value)

    def set_direct_sampling(self, value: int) -> int:
        return self.send_command(0x09, value)

    def set_offset_tuning(self, value: int) -> int:
        return self.send_command(0x0a, value)

    def set_xtal_freq(self, value: int) -> int:
        return self.send_command(0x0b, value)

    def set_tuner_xtal(self, value: int) -> int:
        return self.send_command(0x0c, value)

    def set_tuner_gain_by_index(self, value: int) -> int:
        return self.send_command(0x0d, value)

    def set_set_bias_tee(self, value: int) -> int:
        return self.send_command(0x0e, value)
