#!/usr/bin/env python3

import asyncio
import multiprocessing
import queue
import struct

import numpy as np
import websockets


class TestWebSocketServer(multiprocessing.Process):
    """
    The websocket server.
    """

    def __init__(self):
        multiprocessing.Process.__init__(self)

    def run(self):
        print("Starting test websocket server")
        start_server = websockets.serve(self.time_processor, "127.0.0.1", 5555)

        asyncio.get_event_loop().run_until_complete(start_server)
        asyncio.get_event_loop().run_forever()

        print("WebSocket server process exited")
        return

    async def time_processor(self, websocket, path):
        while True:
            try:
                # timeout on queue read so we can, if we wanted to, exit our forever loop
                sps: int = 123
                centre: int = 456
                spec = np.random.rand(7)
                peak = np.random.rand(7)
                time_start: int = 24 << 32
                time_end: int = 36 << 34

                # pack the data up in binary, watch out for sizes
                message = struct.pack(f"!2i2qi{spec.size}f{spec.size}f",
                                      sps,  # 4bytes
                                      centre,  # 4bytes
                                      time_start,  # 8bytes
                                      time_end,  # 8bytes
                                      spec.size,  # 4bytes (N)
                                      *spec,  # N * 4byte floats (32bit)
                                      *peak)  # N * 4byte floats (32bit)

                await websocket.send(message)
                await asyncio.sleep(1 / 20.0)  # max 20fps, so wait around this long before checking again
            except queue.Empty:
                # unlikely to every keep up so shouldn't end up here
                await asyncio.sleep(0.1)


if __name__ == '__main__':
    w = TestWebSocketServer()
    w.start()
