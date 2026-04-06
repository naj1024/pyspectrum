#!/usr/bin/env python3

import asyncio
import logging
import multiprocessing
import os
import pathlib
import queue
import signal
import struct
import time
from builtins import Exception
from packaging import version

import websockets

from misc import global_vars

logger = logging.getLogger(__name__)

# check the websockets version, upgraded to use 15.0.1
if version.parse(websockets.__version__) < version.parse("15.0.1"):
    raise ValueError(f"websockets version must be >= 15.0.1, got {websockets.__version__}")


class WebSocketServer(multiprocessing.Process):
    def __init__(self,
                 to_ui_queue: multiprocessing.Queue,
                 log_level: int,
                 websocket_port: int):
        multiprocessing.Process.__init__(self)
        self._to_ui_queue = to_ui_queue
        self._port = websocket_port
        print(f"web socket port {self._port}")
        self._exit_now = False
        self._log_level = log_level
        self._active_connection = None

    def shutdown(self) -> None:
        logger.debug("WebSocketServer Shutting down")
        self._exit_now = True
        try:
            asyncio.get_event_loop().call_soon_threadsafe(asyncio.get_event_loop().stop)
        except Exception as msg:
            logger.error(f"Exception when closing websocket, {msg}")
        logger.debug("WebSocketServer shutdown")

    def signal_handler(self, _sig, __):
        self.shutdown()

    def run(self):

        # as we are in a separate process the thing that spawned us can't call shutdown correctly
        # It can send us a signal, then we can shut down our self
        signal.signal(signal.SIGINT, self.signal_handler)


        global logger
        log_file = pathlib.PurePath(os.path.dirname(__file__), "..", global_vars.log_dir, __name__ + ".log")

        try:
            file_handler = logging.FileHandler(log_file, mode="w")
        except Exception as msg:
            print(f"Failed to create logger for websocket, {msg}")
            exit(1)

        formatter = logging.Formatter('%(asctime)s,%(levelname)s:%(name)s:%(module)s:%(message)s',
                                      datefmt="%Y-%m-%d %H:%M:%S UTC")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logging.Formatter.converter = time.gmtime
        logger.setLevel(self._log_level)

        logger.info(f"WebSocket starting on port {self._port}")

        # Explicitly create and set the event loop
        import functools
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def server_task():
            try:
                async with websockets.serve(
                        functools.partial(self.handler), "0.0.0.0", self._port
                ):
                    logger.info("WebSocket server is now listening")
                    while not self._exit_now:
                        await asyncio.sleep(0.5)
            except Exception as msg:
                logger.error(f"Exception when closing websocket, {msg}")

        try:
            loop.run_until_complete(server_task())
        except Exception as msg:
            logger.error(f"WebSocket exception: {msg}")
        finally:
            loop.close()
            logger.info("WebSocket process exited")

    async def handler(self, web_socket):
        # path = web_socket.path

        if self._active_connection is not None:
            try:
                await self._active_connection.send("Closing this stream, another client has requested it")
                await self._active_connection.close()
                logger.info(f"Closed websocket to {self._active_connection.remote_address[0]}")
            except Exception as msg:
                logger.error(f"Exception when closing websocket, {msg}")

        self._active_connection = web_socket
        client = web_socket.remote_address[0]
        logger.info(f"WebSocket serving client {client}")

        tx_task = asyncio.ensure_future(self.tx_handler(web_socket))
        done, pending = await asyncio.wait(
            [tx_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        logger.info(f"WebSocket exited serving client {client}")

    async def tx_handler(self, web_socket):
        client = web_socket.remote_address[0]
        logger.info(f"web socket Tx for client {client}")

        try:
            while not self._exit_now:
                try:
                    sps, centre, magnitudes, time_start, time_end = self._to_ui_queue.get(timeout=0.1)

                    centre_mhz = float(centre) / 1e6
                    start_sec = int(time_start / 1e9)
                    start_nsec = int(time_start - start_sec * 1e9)
                    end_sec = int(time_end / 1e9)
                    end_nsec = int(time_end - end_sec * 1e9)

                    num_floats = int(magnitudes.size)
                    data_type = 1
                    message = struct.pack(
                        f"!2id5i{num_floats}f",
                        int(data_type),
                        int(sps),
                        centre_mhz,
                        int(start_sec),
                        int(start_nsec),
                        int(end_sec),
                        int(end_nsec),
                        num_floats,
                        *magnitudes
                    )

                    await web_socket.send(message)

                except queue.Empty:
                    pass

                await asyncio.sleep(0.001)

        except Exception as msg:
            logger.error(f"WebSocket socket Tx exception for {client}, {msg}")
