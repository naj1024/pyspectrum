#!/usr/bin/env python3

import asyncio
import json
import multiprocessing
import queue
import struct
import logging
import time

import websockets
from websockets import WebSocketServerProtocol

# for logging in the webSocket
logger = None

DEFAULT_FPS = 20.0


class WebSocketServer(multiprocessing.Process):
    """
    The web socket server.
    """

    def __init__(self,
                 data_queue: multiprocessing.Queue,
                 control_queue: multiprocessing.Queue,
                 log_level: int,
                 websocket_port: int):
        """
        Configure the basics of this class

        :param data_queue: we will receive structured data from this queue
        :param control_queue: Future use as data to be sent back from whatever UI will hang of us
        :param log_level: The logging level we wish to use
        :param websocket_port: The port the web socket will be on
        """
        multiprocessing.Process.__init__(self)
        self._data_queue = data_queue
        self._control_queue = control_queue
        self._port = websocket_port
        self._exit_now = False
        self._fps = DEFAULT_FPS
        self._log_level = log_level

    def exit_loop(self) -> None:
        self._exit_now = True
        # https://www.programcreek.com/python/example/94580/websockets.serve example 5
        asyncio.get_event_loop().call_soon_threadsafe(asyncio.get_event_loop().stop)

    def run(self):
        """
        The process start method
        :return: None
        """
        # logging to our own logger, not the base one - we will not see log messages for imported modules
        global logger
        logger = logging.getLogger('web_socket_logger')
        # don't use %Z for timezone as some say 'GMT' or 'GMT standard time'
        logging.basicConfig(format='%(asctime)s,%(levelname)s:%(name)s:%(module)s:%(message)s',
                            datefmt="%Y-%m-%d %H:%M:%S UTC",
                            filemode='w',
                            filename="websocket.log")
        logging.Formatter.converter = time.gmtime  # GMT/UTC timestamps on logging
        logger.setLevel(self._log_level)

        logger.info(f"WebSocket starting on port {self._port}")
        start_server = websockets.serve(self.handler, "0.0.0.0", self._port)

        asyncio.get_event_loop().run_until_complete(start_server)
        asyncio.get_event_loop().run_forever()

        logger.error("WebSocket server process exited")
        return

    async def handler(self, web_socket: WebSocketServerProtocol, path: str):
        """
        Handle both Rx and Tx to the client on of the websocket

        Tx goes from us (_data_queue) to the web client
        Rx comes from the web client to us (_control_queue)

        :param web_socket:
        :param path: Not used, default is '/'
        :return: None
        """

        client = web_socket.remote_address[0]
        logger.info(f"WebSocket serving client {client} {path}")

        tx_task = asyncio.ensure_future(
            self.tx_handler(web_socket))
        rx_task = asyncio.ensure_future(
            self.rx_handler(web_socket))
        done, pending = await asyncio.wait(
            [tx_task, rx_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        logger.info(f"WebSocket exited serving client {client} {path}")

    async def rx_handler(self, web_socket: WebSocketServerProtocol):
        """
        Receive JSON data from the client

        :param web_socket: The client connection
        :return: None
        """

        client = web_socket.remote_address[0]
        logger.info(f"web socket Rx for client {client}")
        try:
            async for message in web_socket:
                # message are json e.g.
                # {"name":"unknown","centreFrequencyHz":433799987.79296875,"sps":1500000,"bw":1500000,
                #                   "fftSize":"8192","sdrStateUpdated":false}
                # {"type":"fps","updated":true,"value":"10"}
                mess = json.loads(message)
                if mess['type'] == "fps":
                    self._fps = int(mess['value'] * 2)  # read twice as fast as data being put in, stops stuttering

                self._control_queue.put(message, timeout=0.1)

        except Exception as msg:
            logger.error(f"WebSocket socket Rx exception for {client}, {msg}")

    async def tx_handler(self, web_socket: WebSocketServerProtocol):
        """
        Send data packed binary data to the client

        :param web_socket: The client connection
        :return: None
        """

        client = web_socket.remote_address[0]
        logger.info(f"web socket Tx for client {client}")
        # NOTE this is not going to end
        try:
            while not self._exit_now:
                try:
                    # timeout on queue read so we can, if we wanted to, exit our forever loop
                    state, sps, centre, magnitudes, time_start, time_end = self._data_queue.get(timeout=0.1)

                    # if we have the state then just send this, ignore the rest
                    if state:
                        await web_socket.send(state)  # it is json
                    else:
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

                        # TODO: Not happy with this algorithm
                        # wait 1/fps before proceeding
                        # The problem is that the network/OS will buffer things for us if we go really fast
                        # we then take lots of memory and can't break out of the processing
                        # using asyncio.sleep() allows web_socket to service connections etc
                        # We can end up with NO sleep, locks browser up and takes loads of memory
                        end_time = time.time() + (1 / self._fps)
                        while (end_time - time.time()) > 0:
                             await asyncio.sleep(1 / self._fps)  # we will not sleep this long

                except queue.Empty:
                    # unlikely to every keep up so shouldn't end up here
                    await asyncio.sleep(0.1)

        except Exception as msg:
            logger.error(f"WebSocket socket Tx exception for {client}, {msg}")
