#!/usr/bin/env python3

import asyncio
import logging
import multiprocessing
import os
import pathlib
import queue
import struct
import time
from builtins import Exception

import websockets
from websockets import WebSocketServerProtocol

from misc import global_vars

# for logging in the webSocket
logger = logging.getLogger(__name__)


class WebSocketServer(multiprocessing.Process):
    """
    The web socket server.
    """

    def __init__(self,
                 to_ui_queue: multiprocessing.Queue,
                 log_level: int,
                 websocket_port: int,
                 config: dict):
        """
        Configure the basics of this class

        :param to_ui_queue: we will receive structured spectrum data from this queue
        :param log_level: The logging level we wish to use
        :param websocket_port: The port the web socket will be on
        """
        multiprocessing.Process.__init__(self)
        self._to_ui_queue = to_ui_queue
        self._port = websocket_port
        self._exit_now = False
        self._log_level = log_level

    def shutdown(self) -> None:
        logger.debug("WebSocketServer Shutting down")
        self._exit_now = True
        # https://www.programcreek.com/python/example/94580/websockets.serve example 5
        asyncio.get_event_loop().call_soon_threadsafe(asyncio.get_event_loop().stop)
        logger.debug("WebSocketServer shutdown")

    def run(self):
        """
        The process start method
        :return: None
        """
        # logging to our own logger, not the base one - we will not see log messages for imported modules
        global logger
        log_file = pathlib.PurePath(os.path.dirname(__file__), "..", global_vars.log_dir, __name__ + ".log")

        try:
            # define file handler and set formatter
            file_handler = logging.FileHandler(log_file, mode="w")
        except Exception as msg:
            print(f"Failed to create logger for websocket, {msg}")
            exit(1)

        formatter = logging.Formatter('%(asctime)s,%(levelname)s:%(name)s:%(module)s:%(message)s',
                                      datefmt="%Y-%m-%d %H:%M:%S UTC")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        # don't use %Z for timezone as some say 'GMT' or 'GMT standard time'
        logging.Formatter.converter = time.gmtime  # GMT/UTC timestamps on logging
        logger.setLevel(self._log_level)

        logger.info(f"WebSocket starting on port {self._port}")
        while not self._exit_now:
            try:
                start_server = websockets.serve(self.handler, "0.0.0.0", self._port)

                asyncio.get_event_loop().run_until_complete(start_server)
                asyncio.get_event_loop().run_forever()
            except Exception as msg:
                logger.error(f"WebSocket {msg}")
                time.sleep(1)

        logger.error("WebSocket server process exited")
        return

    async def handler(self, web_socket: WebSocketServerProtocol, path: str):
        """
        Handle Tx to the client on the websocket

        Tx goes from us (_data_queue) to the web client

        :param web_socket:
        :param path: Not used, default is '/'
        :return: None
        """

        client = web_socket.remote_address[0]
        logger.info(f"WebSocket serving client {client} {path}")

        tx_task = asyncio.ensure_future(
            self.tx_handler(web_socket))
        done, pending = await asyncio.wait(
            [tx_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        logger.info(f"WebSocket exited serving client {client} {path}")

    async def tx_handler(self, web_socket: WebSocketServerProtocol):
        """
        Send data to the UI client

        :param web_socket: The client connection
        :return: None
        """

        client = web_socket.remote_address[0]
        logger.info(f"web socket Tx for client {client}")

        # NOTE this is not going to end until:
        # websocket connection exceptions - probably closed
        # we force an exit
        try:
            while not self._exit_now:
                # timeout on queue read so we can, if we wanted to, exit our forever loop
                try:
                    sps, centre, magnitudes, time_start, time_end = self._to_ui_queue.get(timeout=0.1)

                    centre_mhz = float(centre) / 1e6  # in MHz

                    # times are in nsec and javascript won't handle 8byte int so break it up
                    start_sec: int = int(time_start / 1e9)
                    start_nsec: int = int(time_start - start_sec * 1e9)
                    end_sec: int = int(time_end / 1e9)
                    end_nsec: int = int(time_end - end_sec * 1e9)

                    num_floats = int(magnitudes.size)
                    # pack the data up in binary, watch out for sizes
                    # ignoring times for now as still to handle 8byte ints in javascript
                    # !2id5i{num_floats}f{num_floats}f is in network order 2 int, 1 double, 5 int, N float
                    data_type: int = 1  # magnitude data
                    message = struct.pack(f"!2id5i{num_floats}f",  # format
                                          int(data_type),  # 4bytes
                                          int(sps),  # 4bytes
                                          centre_mhz,  # 8byte double float (64bit)
                                          int(start_sec),  # 4bytes
                                          int(start_nsec),  # 4bytes
                                          int(end_sec),  # 4bytes
                                          int(end_nsec),  # 4bytes
                                          num_floats,  # 4bytes (N)
                                          *magnitudes)  # N * 4byte floats (32bit)

                    await web_socket.send(message)

                except queue.Empty:
                    # no data for us yet
                    pass

                await asyncio.sleep(0.001)  # max 1000fps !

        except Exception as msg:
            logger.error(f"WebSocket socket Tx exception for {client}, {msg}")
