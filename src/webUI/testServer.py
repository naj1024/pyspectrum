#!/usr/bin/env python3

import asyncio
import multiprocessing
import queue
import struct

import numpy as np
import websockets


class TestWebSocketServer(multiprocessing.Process):
    """
    The web socket server.
    """

    def __init__(self):
        multiprocessing.Process.__init__(self)

    def run(self):
        print("Starting test web socket server")
        start_server = websockets.serve(self.time_processor, "127.0.0.1", 5555)

        asyncio.get_event_loop().run_until_complete(start_server)
        asyncio.get_event_loop().run_forever()

        print("WebSocket server process exited")
        return

    async def time_processor(self, web_socket, path):
        while True:
            try:
                sps: int = 123
                centre: int = 456
                num_floats = 2048
                mags = np.random.rand(num_floats)
                mags = 10 * np.log10(mags)
                peaks = np.random.rand(num_floats)
                peaks = 10 * np.log10(peaks)
                time_start: int = 24  # supposed to be 8bytes but js doesn't have a converter for things that big
                time_end: int = 36

                # pack the data up in binary, watch out for sizes
                message = struct.pack(f"!5i{num_floats}f{num_floats}f",
                                      sps,  # 4bytes
                                      centre,  # 4bytes
                                      time_start,  # 4bytes
                                      time_end,  # 4bytes
                                      num_floats,  # 4bytes (N)
                                      *mags,  # N * 4byte floats (32bit)
                                      *peaks)  # N * 4byte floats (32bit)

                await web_socket.send(message)
                await asyncio.sleep(1)
            except queue.Empty:
                # unlikely to every keep up so shouldn't end up here
                await asyncio.sleep(0.1)


if __name__ == '__main__':
    w = TestWebSocketServer()
    w.start()
