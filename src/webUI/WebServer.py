#!/usr/bin/env python3

import http.server
import pathlib
import socketserver
import os
import multiprocessing
import logging
import time
import signal

from webUI import WebSocketServer
from misc import global_vars

# root is directory relative to our source file
web_root = f"{os.path.dirname(__file__)}/webroot/"

# for logging in the webserver
logger = logging.getLogger(__name__)


class _Handler(http.server.SimpleHTTPRequestHandler):
    """
    Handle a connection
    """

    def __init__(self, *args, **kwargs):
        try:
            global web_root
            os.chdir(web_root)  # don't use directory=web_root as not supported until python 3.8
            super().__init__(*args, **kwargs)
        except Exception as msg:
            logger.error(f"http handler error, {msg}")
            pass


class WebServer(multiprocessing.Process):
    """
    Serves the html and javascript for the client browsers to use
    Spawns off a web socket server as a separate process.
    """

    def __init__(self,
                 to_ui_queue: multiprocessing.Queue,
                 to_ui_control_queue: multiprocessing.Queue,
                 from_ui_queue: multiprocessing.Queue,
                 log_level: int,
                 web_port: int):
        """
        Initialise the web server

        :param to_ui_queue: we pass it to a web socket server
        :param to_ui_control_queue: we pass it to a web socket server
        :param from_ui_queue: we pass it to a web socket server
        :param log_level: The logging level we wish to use
        :param web_port: The port the web server will serve on
        """
        multiprocessing.Process.__init__(self)

        # queues are for the web socket, not used in the web server
        self._to_ui_queue = to_ui_queue
        self._to_ui_control_queue = to_ui_control_queue
        self._from_ui_queue = from_ui_queue
        self._port = web_port
        self._httpd = None
        self._web_socket_server = None
        self._log_level = log_level
        self._shutdown = False

    def shutdown(self):
        logger.debug("WebServer Shutting down")
        self._shutdown = True
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
        log_file = pathlib.PurePath(os.path.dirname(__file__), "..", global_vars.log_dir, __name__ + ".log")

        try:
            # define file handler and set formatter
            file_handler = logging.FileHandler(log_file, mode="w")
        except Exception as msg:
            print(f"Failed to create logger for webserver, {msg}")
            exit(1)

        formatter = logging.Formatter('%(asctime)s,%(levelname)s:%(name)s:%(module)s:%(message)s',
                                      datefmt="%Y-%m-%d %H:%M:%S UTC")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        # don't use %Z for timezone as some say 'GMT' or 'GMT standard time'
        logging.Formatter.converter = time.gmtime  # GMT/UTC timestamps on logging
        logger.setLevel(self._log_level)

        # as we are in a separate process the thing that spawned us can't call shutdown correctly
        # but it can send us a signal, then we can shutdown our self
        signal.signal(signal.SIGINT, self.signal_handler)

        logger.info(f"Web server serving on port {self._port}")

        # start a web socket server for the remote client to connect to
        #  must be done here not in __init__ as otherwise fork/etc would stop it working as expected
        self._web_socket_server = WebSocketServer.WebSocketServer(self._to_ui_queue, self._to_ui_control_queue,
                                                                  self._from_ui_queue, logger.level, self._port + 1)
        self._web_socket_server.start()

        global web_root
        while not self._shutdown:
            try:
                logger.info(f"web server serving {web_root} on port {self._port}")
                with socketserver.ThreadingTCPServer(("", self._port), _Handler) as self._httpd:
                    self._httpd.serve_forever()
            except Exception as msg:
                logger.error(f"WebServer {msg}")
                time.sleep(1)

        logger.error("WebServer process exited")
        return
