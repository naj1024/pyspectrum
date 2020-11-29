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
help_string = f"{module_type}:IP:port - The Ip or resolvable name and port of an rtltcp server, " \
              f"e.g. {module_type}:192.168.2.1:12345"
web_help_string = "IP:port - The Ip or resolvable name and port of an rtltcp server, e.g. 192.168.2.1:12345"


# return an error string if we are not available
def is_available() -> Tuple[str, str]:
    return module_type, ""


# The following must match the rtl_sdr C source code definitions in rtl_sdr.h for enum rtlsdr_tuner{}
allowed_tuner_types = ["Unknown", "E4000", "FC0012", "FC0013", "FC2580", "R820T", "R828D"]


class Input(DataSource.DataSource):

    def __init__(self,
                 source: str,
                 number_complex_samples: int,
                 data_type: str,
                 sample_rate: float,
                 centre_frequency: float,
                 sleep_time: float):
        """
        The rtltcp input source

        :param source: Ip and port as a string, e.g. 127.0.0.1:3456
        :param number_complex_samples: The number of complex samples we require each request
        :param data_type: ignored, we will be getting 8bit offset binary, '8o'
        :param sample_rate: The sample rate we will set the source to, note true sps is set from the device
        :param centre_frequency: The centre frequency the source will be set to
        :param sleep_time: Time in seconds between reads, not used on most sources
        """
        self._constant_data_type = "8o"
        super().__init__(source, number_complex_samples, self._constant_data_type, sample_rate,
                         centre_frequency, sleep_time)

        self._socket = None
        self._connected = False
        self._tuner_type_str = "Unknown_Tuner"
        self._ip_address = ""
        self._ip_port = 0
        self._gain_modes = ["auto", "manual"]  # would ask, but can't
        super().set_gain_mode(self._gain_modes[0])
        super().set_help(help_string)
        super().set_web_help(web_help_string)

    def open(self) -> bool:
        # specifics to this class
        # break apart the ip address and port, will be something like 192.168.0.1:1234

        parts = self._source.split(':')
        if len(parts) <= 2:
            raise ValueError("input specification does not contain two colon separated items, "
                             f"{self._source}")
        self._ip_address = parts[0]
        try:
            self._ip_port = int(parts[1])
        except ValueError as msg1:
            msgs = f"port number from {parts[1]}, {msg1}"
            self._error = str(msgs)
            logger.error(msgs)
            raise ValueError(msgs)

        if self._ip_port < 0:
            msgs = f"port number from {parts[1]} is negative"
            self._error = msgs
            logger.error(msgs)
            raise ValueError(msgs)

        self._socket = None
        self._connected = False
        self._tuner_type_str = "Unknown_Tuner"

        return self._connected

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
        try:
            self._connected = self.connect()
        except ValueError as msg:
            self._error = str(msg)
            raise ValueError(msg)

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

            # recover the type of tuner we have from the server
            self._tuner_type_str = self.get_tuner_type()
            self._display_name += f" {self._tuner_type_str}"

            # say what we want
            self.set_sample_rate(int(self._sample_rate))
            self.set_center_frequency(int(self._centre_frequency))
            # not found a description of gain_mode / agc_mode ...
            self.set_tuner_gain_mode(1)

            # TODO: what's the difference between set_tuner_gain_by_index() and set_tuner_gain() ?
            self.set_tuner_gain_by_index(17)  # ignored unless set_tuner_gain_mode is 1
            self.set_agc_mode(0)
        except Exception as msg:
            logger.error(msg)
            raise ValueError(msg)

        return self._connected

    def get_tuner_type(self) -> str:
        """
        Read the first bytes after a rtl_tcp connection to recover the tuner type

        The initial bytes contain the dongle_info_t defined in rtl_tcp.c

        magic is 'RTL0'

        typedef struct { /* structure size must be multiple of 2 bytes */
                char magic[4];
                uint32_t tuner_type;
                uint32_t tuner_gain_count;
            } dongle_info_t;

            rtl_sdr.h
            enum rtlsdr_tuner {
                RTLSDR_TUNER_UNKNOWN = 0,
                RTLSDR_TUNER_E4000,
                RTLSDR_TUNER_FC0012,
                RTLSDR_TUNER_FC0013,
                RTLSDR_TUNER_FC2580,
                RTLSDR_TUNER_R820T,
                RTLSDR_TUNER_R828D
            };

        :return The tuner type as a string:
        """
        tuner_type_str = ""
        dongle_info, _ = self.get_bytes(12)  # 12 bytes, 4 chars + 2 unint32
        # unpack as network order, 4 chars and 2 unsigned integers
        try:
            magic, tuner_type, tuner_gain_count = struct.unpack('!4s2I', dongle_info)
            if magic == b"RTL0" and tuner_type < len(allowed_tuner_types):
                tuner_type_str = allowed_tuner_types[tuner_type]
            else:
                self._error = f"Unknown RTL tuner {magic} or type {tuner_type}"
                logger.error(f"Unknown RTL tuner {magic} or type {tuner_type}")
        except Exception as fff:
            raise ValueError(fff)

        logger.info(f"{tuner_type_str} tuner")
        return tuner_type_str

    def get_bytes(self, bytes_to_get: int) -> Tuple[bytearray, float]:
        """
        Read bytes_to_get bytes from the server

        :param bytes_to_get: Number of bytes to get from the server
        :return: A Tuple of bytearray of the bytes and time the bytes were received
        """
        rx_time = 0
        try:
            raw_bytes = bytearray()
            while bytes_to_get > 0:
                got: bytearray = self._socket.recv(bytes_to_get)  # will get a MAXIMUM of this number of bytes
                if rx_time == 0:
                    rx_time = self.get_time_ns()
                if len(got) == 0:
                    self._socket.close()
                    self._connected = False
                    logger.info('rtltcp connection closed')
                    raise ValueError('rtltcp connection closed')
                raw_bytes += got
                bytes_to_get -= len(got)

        except OSError as msg1:
            if self._socket:
                self._socket.close()
            msgs = f'OSError, {msg1}'
            self._error = str(msgs)
            logger.error(msgs)
            self._connected = False
            raise ValueError(msgs)

        return raw_bytes, rx_time

    def set_sample_type(self, data_type: str) -> None:
        # we can't set a different sample type on this source
        super().set_sample_type(self._constant_data_type)

    def set_gain(self, gain: float) -> None:
        self._gain = gain
        try:
            self.set_tuner_gain_mode(int(gain))
        except Exception as msg:
            self._error = str(msg)
            raise ValueError(msg)

    def set_gain_mode(self, mode: str) -> None:
        if mode in self._gain_modes:
            self._gain_mode = mode
            if mode == "auto":
                self.set_tuner_gain_mode(0)
            else:
                self.set_tuner_gain_mode(1)

    def read_cplx_samples(self) -> Tuple[np.array, float]:
        """
        Return complex float samples from the device

        :return: A tuple of a numpy array of complex samples and time in nsec
        """
        complex_data = None
        rx_time = 0

        if self._connected:
            raw_bytes, rx_time = self.get_bytes(self._bytes_per_snap)
            if len(raw_bytes) == self._bytes_per_snap:
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

    def set_center_frequency(self, frequency: int) -> int:
        # limits depend on tuner type: from https://wiki.radioreference.com/index.php/RTL-SDR
        # Tuner 	             Frequency Range
        # =======================================
        # Elonics E4000 	     52 – 1100 MHz / 1250 - 2200 MHz
        # Rafael Micro R820T(2)  24 – 1766 MHz
        # Fitipower FC0013 	     22 – 1100 MHz
        # Fitipower FC0012 	     22 - 948.6 MHz
        # FCI FC2580 	         146 – 308 MHz / 438 – 924 MHz

        # what type of tuner do we have ?
        freq_ok = True
        freq_range = ""
        if self._tuner_type_str == allowed_tuner_types[1]:
            # E4000
            if (frequency < 52e6) or (frequency > 2200e6):
                freq_ok = False
                freq_range = "52 – 1100 MHz and 1250 - 2200 MHz"
            elif (frequency > 1100e6) and (frequency < 1250e6):
                freq_ok = False
                freq_range = "52 – 1100 MHz and 1250 - 2200 MHz"
        elif self._tuner_type_str == allowed_tuner_types[2]:
            # FC0012
            if (frequency < 22e6) or (frequency > 948.6e6):
                freq_ok = False
                freq_range = "22 - 948.6 MHz"
        elif self._tuner_type_str == allowed_tuner_types[3]:
            # FC0013
            if (frequency < 22e6) or (frequency > 1100e6):
                freq_ok = False
                freq_range = "22 – 1100 MHz"
        elif self._tuner_type_str == allowed_tuner_types[4]:
            # FC2580
            if (frequency < 146e6) or (frequency > 924e6):
                freq_ok = False
                freq_range = "146 – 308 MHz and 438 – 924 MHz"
            elif (frequency > 308e6) and (frequency < 438e6):
                freq_ok = False
                freq_range = "146 – 308 MHz and 438 – 924 MHz"
        elif self._tuner_type_str == allowed_tuner_types[5] or self._tuner_type_str == allowed_tuner_types[6]:
            # R820T or R828D
            if (frequency < 24e6) or (frequency > 1.766e9):
                freq_ok = False
                freq_range = "24 – 1766 MHz"

        if not freq_ok:
            err = f"{self._tuner_type_str}, {frequency}Hz outside range {freq_range}"
            self._error = err
            logger.error(err)
            frequency = 600e6  # something safe

        logger.info(f"Set frequency {frequency / 1e6:0.6f}MHz")
        self._centre_frequency = frequency
        return self.send_command(0x01, frequency)

    def set_sample_rate(self, sample_rate: int) -> int:
        # rtlsdr has limits on allowed sample rates
        # from librtlsdr.c data_source.get_bytes_per_sample()
        # 	/* check if the rate is supported by the resampler */
        # 	if ((samp_rate <= 225000) || (samp_rate > 3200000) ||
        # 	   ((samp_rate > 300000) && (samp_rate <= 900000))) {
        # 		fprintf(stderr, "Invalid sample rate: %u Hz\n", samp_rate);
        # 		return -EINVAL;
        # 	}
        # We have no way of knowing if a command completes on the remote platform
        if (sample_rate <= 225000) or (sample_rate > 3200000) or ((sample_rate > 300000) and (sample_rate <= 900000)):
            err = f"{module_type} invalid sample rate, {sample_rate}sps"
            self._error = err
            logger.error(err)
            sample_rate = int(1e6)
        self._sample_rate = sample_rate
        logger.info(f"Set sample rate {sample_rate}sps")
        return self.send_command(0x02, sample_rate)

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
