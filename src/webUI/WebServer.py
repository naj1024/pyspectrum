#!/usr/bin/env python3

import http.server
import socketserver
import os
import multiprocessing
import logging
import time
import signal

from webUI import WebSocketServer

# root is directory relative to our source file
web_root = f"{os.path.dirname(__file__)}/webroot/"

logger = logging.getLogger('web_server_logger')
logger.setLevel(logging.ERROR)


class _Handler(http.server.SimpleHTTPRequestHandler):
    """
    Handle a connection
    """

    def __init__(self, *args, **kwargs):
        global web_root
        os.chdir(web_root) # don't use directory=web_root as not supported until python 3.8
        super().__init__(*args, **kwargs)


class WebServer(multiprocessing.Process):
    """
    Serves the html and javascript for the client browsers to use
    Spawns off a web socket server as a separate process.
    """

    def __init__(self,
                 data_queue: multiprocessing.Queue,
                 control_queue: multiprocessing.Queue,
                 log_level: int):
        """
        Initialise the web server

        :param data_queue: The queue data will arrive on, we do not use it but pass it to a web socket server
        :param control_queue: Data back from whatever is the UI, not used yet
        :param log_level: The logging level we wish to use
        """
        multiprocessing.Process.__init__(self)

        # queues are for the web socket, not used in the web server
        self._data_queue = data_queue
        self._control_queue = control_queue
        self._port = 8080
        self._httpd = None
        self._web_socket_server = None
        logger.setLevel(log_level)

    def shutdown(self):
        if self._httpd:
            self._httpd.shutdown()
        if self._web_socket_server:
            self._web_socket_server.exit_loop()
            while self._web_socket_server.is_alive():
                self._web_socket_server.kill()
                time.sleep(1)

    def signal_handler(self, sig, __):
        self.shutdown()

    def run(self):
        """
        Run the web server process
        :return: None
        """
        # as we are in a separate process the thing that spawned us can't call shutdown correctly
        # but it can send us a signal, then we can shutdown our self
        signal.signal(signal.SIGINT, self.signal_handler)

        logger.info(f"We server serving on port {self._port}")

        #  must be done here not in __init__ as otherwise fork/etc would stop it working as expected
        self._web_socket_server = WebSocketServer.WebSocketServer(self._data_queue, self._control_queue, logger.level)
        self._web_socket_server.start()

        global web_root
        logger.info(f"web server serving {web_root} on port {self._port}")
        with socketserver.TCPServer(("", self._port), _Handler) as self._httpd:
            self._httpd.serve_forever()

        logger.error("Web server process exited")
        return
