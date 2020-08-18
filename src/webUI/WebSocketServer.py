#!/usr/bin/env python3

import asyncio
import multiprocessing
import queue
import struct
import logging
import time

import websockets

logger = logging.getLogger('web_socket_logger')
logger.setLevel(logging.ERROR)

MAX_FPS = 20.0


class WebSocketServer(multiprocessing.Process):
    """
    The web socket server.
    """

    def __init__(self,
                 data_queue: multiprocessing.Queue,
                 control_queue: multiprocessing.Queue,
                 log_level: int):
        """
        Configure the basics of this class

        :param data_queue: we will receive structured data from this queue
        :param control_queue: Future use as data to be sent back from whatever UI will hang of us
        :param log_level: The logging level we wish to use
        """
        multiprocessing.Process.__init__(self)
        self._data_queue = data_queue
        self._control_queue = control_queue
        self._port = 5555
        self._exit_now = False

        logger.setLevel(log_level)

    def exit_loop(self) -> None:
        self._exit_now.set()

    def run(self):
        """
        The process start method
        :return: None
        """
        logger.info(f"Web Socket starting on port {self._port}")
        start_server = websockets.serve(self.serve_connection, "0.0.0.0", self._port)

        asyncio.get_event_loop().run_until_complete(start_server)
        asyncio.get_event_loop().run_forever()

        logger.error("Web Socket server process exited")
        return

    async def serve_connection(self, web_socket, path):
        """
        Serve a connection passed to us

        :param web_socket: The client connection
        :param path: not used
        :return: None
        """
        client = web_socket.remote_address[0]
        logger.info(f"web socket serving client {client}")
        # NOTE this is not going to end
        try:
            while not self._exit_now:
                try:
                    # timeout on queue read so we can, if we wanted to, exit our forever loop
                    # only sending the peak spectrum so ignore the current magnitudes
                    display_on, sps, centre, _, peaks, time_start, time_end = self._data_queue.get(timeout=0.1)

                    centre_MHz = float(centre) / 1e6  # in MHz

                    # times are in nsec and javascript won't handle 8byte int so break it up
                    start_sec: int = int(time_start / 1e9)
                    start_nsec: int = int(time_start - start_sec * 1e9)
                    end_sec: int = int(time_end / 1e9)
                    end_nsec: int = int(time_end - end_sec * 1e9)

                    num_floats = int(peaks.size)
                    # pack the data up in binary, watch out for sizes
                    # ignoring times for now as still to handle 8byte ints in javascript
                    # !if5i{num_floats}f{num_floats}f is in network order 1 int, 1 float, 5 int, N float
                    message = struct.pack(f"!if5i{num_floats}f",
                                          int(sps),  # 4bytes
                                          float(centre_MHz),  # 4byte float (32bit)
                                          int(start_sec),  # 4bytes
                                          int(start_nsec),  # 4bytes
                                          int(end_sec),  # 4bytes
                                          int(end_nsec),  # 4bytes
                                          num_floats,  # 4bytes (N)
                                          *peaks)  # N * 4byte floats (32bit)

                    # send it off to the client
                    await web_socket.send(message)

                    # wait 1/fps before proceeding - this limits us to this fps
                    # sleep using asyncio allows web_socket to service connections etc
                    end_time = time.time() + (1 / MAX_FPS)
                    while (end_time - time.time()) > 0:
                        await asyncio.sleep(1 / MAX_FPS)  # we will not sleep this long

                except queue.Empty:
                    # unlikely to every keep up so shouldn't end up here
                    await asyncio.sleep(0.1)

        except Exception as msg:
            logger.info(f"web socket ended for {client}, {msg}")
