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

# for logging in the webserver
logger = logging.getLogger('web_server_logger')


class _Handler(http.server.SimpleHTTPRequestHandler):
    """
    Handle a connection
    """

    def __init__(self, *args, **kwargs):
        global web_root
        os.chdir(web_root)  # don't use directory=web_root as not supported until python 3.8
        super().__init__(*args, **kwargs)


class WebServer(multiprocessing.Process):
    """
    Serves the html and javascript for the client browsers to use
    Spawns off a web socket server as a separate process.
    """

    def __init__(self,
                 data_queue: multiprocessing.Queue,
                 control_queue: multiprocessing.Queue,
                 log_level: int,
                 web_port: int):
        """
        Initialise the web server

        :param data_queue: The queue data will arrive on, we do not use it but pass it to a web socket server
        :param control_queue: Data back from whatever is the UI, not used yet
        :param log_level: The logging level we wish to use
        :param web_port: The port the web server will serve on
        """
        multiprocessing.Process.__init__(self)

        # queues are for the web socket, not used in the web server
        self._data_queue = data_queue
        self._control_queue = control_queue
        self._port = web_port
        self._httpd = None
        self._web_socket_server = None
        self._log_level = log_level

    def shutdown(self):
        logger.debug("WebServer Shutting down")
        if self._httpd:
            self._httpd.shutdown()

        if self._web_socket_server:
            logger.debug(
                f"Webserver is shutting down WebSocketServer {self._web_socket_server}, "
                f"children {multiprocessing.active_children()}")
            self._web_socket_server.exit_loop()
            if multiprocessing.active_children():
                # belt and braces
                self._web_socket_server.terminate()
                self._web_socket_server.shutdown()
                self._web_socket_server.join()
            logger.debug("WebServer thinks WebSocketServer shut down ?")

        logger.debug("WebServer shutdown")

    def signal_handler(self, sig, __):
        self.shutdown()

    def run(self):
        """
        Run the web server process
        :return: None
        """
        global logger
        # don't use %Z for timezone as some say 'GMT' or 'GMT standard time'
        logging.basicConfig(format='%(asctime)s,%(levelname)s:%(name)s:%(module)s:%(message)s',
                            datefmt="%Y-%m-%d %H:%M:%S UTC",
                            filemode='w',
                            filename="webserver.log")
        logging.Formatter.converter = time.gmtime  # GMT/UTC timestamps on logging
        logger.setLevel(self._log_level)

        # as we are in a separate process the thing that spawned us can't call shutdown correctly
        # but it can send us a signal, then we can shutdown our self
        signal.signal(signal.SIGINT, self.signal_handler)

        logger.info(f"Web server serving on port {self._port}")

        # start a web socket server for the remote client to connect to
        #  must be done here not in __init__ as otherwise fork/etc would stop it working as expected
        self._web_socket_server = WebSocketServer.WebSocketServer(self._data_queue, self._control_queue,
                                                                  logger.level, self._port+1)
        self._web_socket_server.start()

        logger.info(f"WebServer started WebSocketServer, {self._web_socket_server}")

        global web_root
        logger.info(f"web server serving {web_root} on port {self._port}")
        with socketserver.ThreadingTCPServer(("", self._port), _Handler) as self._httpd:
            self._httpd.serve_forever()

        logger.error("WebServer process exited")
        return
