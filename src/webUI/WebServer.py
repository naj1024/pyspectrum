#!/usr/bin/env python3

import http.server
import socketserver
import os
import multiprocessing

from webUI import WebSocketServer

PORT = 8080
# root is directory relative to our source file
web_root = os.path.dirname(__file__)


class _Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        global web_root
        super().__init__(*args, directory=web_root, **kwargs)


class WebServer(multiprocessing.Process):
    """
    Serves the html and javascript for the client browsers to use
    Spawns off a web socket server as a separate process.
    """

    def __init__(self,
                 data_queue: multiprocessing.Queue,
                 control_queue: multiprocessing.Queue):
        multiprocessing.Process.__init__(self)

        # queues are for the web socket, not used in the web server
        self._data_queue = data_queue
        self._control_queue = control_queue

    def run(self):
        #  must be done here not in __init__
        web_socket_server = WebSocketServer.WebSocketServer(self._data_queue, self._control_queue)
        web_socket_server.start()

        global web_root
        print(f"serving {web_root} on port {PORT}")
        with socketserver.TCPServer(("", PORT), _Handler) as httpd:
            httpd.serve_forever()

        print("Web server process exited")
        return


if __name__ == '__main__':
    WebServer()
