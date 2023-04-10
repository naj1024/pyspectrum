#!/usr/bin/env python3
import logging
import multiprocessing
import os
import pathlib
import signal
import time

from flask import Flask, request, jsonify
from flask_restful import Resource, Api as Rest_Api

from misc import global_vars

# root is directory relative to our source file
web_root = f"{os.path.dirname(__file__)}/webroot/"

logger = logging.getLogger(__name__)


class FlaskInterface(multiprocessing.Process):
    """
    Flask based server
    Spawns off a web socket server as a separate process.
    """

    def __init__(self,
                 to_ui_queue: multiprocessing.Queue,
                 log_level: int,
                 shared_status: dict,
                 shared_update: dict):
        """
        Initialise the server

        :param to_ui_queue: we pass it to a web socket server
        :param log_level: The logging level we wish to use
        :param shared_status: A dictionary with current status
        :param shared_update: A dictionary with the updates from the UI, will only contain updates
        """
        multiprocessing.Process.__init__(self)

        self._status = shared_status
        self._update = shared_update

        # queues are for the web socket, not used in the web server
        self._to_ui_queue = to_ui_queue
        self._port = shared_status['web_server_port']
        print(f"web server port {self._port}")
        self._httpd = None
        self._log_level = log_level
        self._shutdown = False

    def shutdown(self):
        logger.debug("FlaskServer Shutting down")
        self._shutdown = True
        if self._httpd:
            self._httpd.shutdown()
        logger.debug("FlaskServer shutdown")

    def signal_handler(self, sig, __):
        self.shutdown()

    def run(self):
        """
        Run the web server process
        Also creates the web socket server

        :return: None
        """
        global logger
        self.set_logging(logger)

        # as we are in a separate process the thing that spawned us can't call shutdown correctly
        # It can send us a signal, then we can shut down our self
        signal.signal(signal.SIGINT, self.signal_handler)

        # serve all the pages from the webroot
        flask_app = Flask(__name__,
                          static_url_path='/',
                          static_folder='webroot')

        # remove all logging from the flask server, removes prints of urls to console
        logw = logging.getLogger('werkzeug')
        logw.disabled = True
        flask_app.logger.disabled = True

        rest_api = Rest_Api(flask_app)

        # server the main static web page on empty URL
        @flask_app.route("/", methods=['GET'])
        def index():
            return flask_app.send_static_file('index.html')

        rest_api.add_resource(Input, '/input/<string:thing>', resource_class_kwargs={'status': self._status, 'update':self._update})
        rest_api.add_resource(Digitiser, '/digitiser/<string:thing>', resource_class_kwargs={'status': self._status, 'update':self._update})
        rest_api.add_resource(Spectrum, '/spectrum/<string:thing>', resource_class_kwargs={'status': self._status, 'update':self._update})
        rest_api.add_resource(Control, '/control/<string:thing>', resource_class_kwargs={'status': self._status, 'update':self._update})
        rest_api.add_resource(Snapshot, '/snapshot/<string:thing>', resource_class_kwargs={'status': self._status, 'update':self._update})
        rest_api.add_resource(Tuning, '/tuning/<string:thing>', resource_class_kwargs={'status': self._status, 'update':self._update})

        global web_root
        while not self._shutdown:
            try:
                logger.info(f"flask server serving {web_root} on port {self._port}")
                flask_app.run(host="0.0.0.0", port=self._port, debug=False)

            except Exception as msg:
                logger.error(f"FlaskServer {msg}")
                time.sleep(1)

        logger.error("WebServer process exited")
        return

    def set_logging(self, logg):
        log_file = pathlib.PurePath(os.path.dirname(__file__), "..", global_vars.log_dir, __name__ + ".log")
        try:
            # define file handler and set formatter
            file_handler = logging.FileHandler(log_file, mode="w")

            formatter = logging.Formatter('%(asctime)s,%(levelname)s:%(name)s:%(module)s:%(message)s',
                                          datefmt="%Y-%m-%d %H:%M:%S UTC")
            file_handler.setFormatter(formatter)
            logg.addHandler(file_handler)
        except Exception as msg:
            print(f"Failed to create logger for webserver, {msg}")
            exit(1)
        # don't use %Z for timezone as some say 'GMT' or 'GMT standard time'
        logging.Formatter.converter = time.gmtime  # GMT/UTC timestamps on logging
        logg.setLevel(self._log_level)


###############
#
# classes for different endpoints
#
############


class Input(Resource):
    # Handle all web requests on the /sources endpoint
    def __init__(self, **kwargs):
        # set the dictionary we use for updating things
        self._status = kwargs['status']
        self._update = kwargs['update']
        self._allowed_get_endpoints = ['sources', 'source', 'errors']
        self._allowed_put_endpoints = ['source']

    def get(self, thing):
        if thing in self._allowed_get_endpoints:
            if thing == "errors":
                tmp = ""
                # error entry may not be present
                if thing in self._status.keys():
                    tmp = self._status[thing]
                    self._status[thing] = ""
                return jsonify({thing: tmp})
            else:
                return jsonify({thing: self._status[thing]})
        return f"Endpoint {thing} not supported", 403

    def put(self, thing):
        if thing in self._allowed_put_endpoints:
            if thing == 'source':
                try:
                    s = request.json['source']
                    p = request.json['params']
                    self._update[thing] = {'source': s, 'params': p, 'connected': False}
                except Exception as err:
                    return f"Failed to parse {thing} endpoint", 400
                return "ok"
        return f"Endpoint {thing} not supported", 403


class Digitiser(Resource):
    # Handle all web requests on the /digitiser endpoint
    def __init__(self, **kwargs):
        # set the dictionary we use for updating things
        self._status = kwargs['status']
        self._update = kwargs['update']
        self._allowed_get_endpoints = ['digitiserFrequency', 'digitiserFormats', 'digitiserFormat',
                                       'digitiserSampleRate',
                                       'digitiserBandwidth', 'digitiserPartsPerMillion', 'digitiserGainTypes',
                                       'digitiserGainType',
                                       'digitiserGain']
        self._allowed_put_endpoints = ['digitiserFormat', 'digitiserSampleRate', 'digitiserBandwidth',
                                       'digitiserPartsPerMillion', 'digitiserGainType', 'digitiserGain']

    def get(self, thing):
        # Check for allowed endpoints at this point
        if thing in self._allowed_get_endpoints:
            return jsonify({thing: self._status[thing]})
        return f"Endpoint {thing} not supported", 403

    def put(self, thing):
        if thing in self._allowed_put_endpoints:
            try:
                if thing == 'digitiserFormat':
                    fmt = request.json[thing]
                    if fmt in self._status['digitiserFormats']:
                        self._update[thing] = fmt
                    else:
                        raise ValueError()
                elif thing == 'digitiserSampleRate':
                    # request.form for non json put
                    sps = abs(int(request.json[thing]))
                    self._update[thing] = sps
                elif thing == 'digitiserBandwidth':
                    bw = abs(int(request.json[thing]))
                    self._update[thing] = bw
                elif thing == 'digitiserPartsPerMillion':
                    ppm = float(request.json[thing])
                    self._update[thing] = ppm
                elif thing == 'digitiserGainType':
                    gt = request.json[thing]
                    if gt in self._status['digitiserGainTypes']:
                        self._update[thing] = gt
                    else:
                        raise ValueError()
                elif thing == 'digitiserGain':
                    gn = abs(int(request.json[thing]))
                    self._update[thing] = gn
                return "ok"
            except Exception:
                return "Failed to parse {thing} endpoint", 400
        return f"Endpoint {thing} not supported", 403


class Spectrum(Resource):
    # Handle all web requests on the /spectrum endpoint
    def __init__(self, **kwargs):
        # set the dictionary we use for updating things
        self._status = kwargs['status']
        self._update = kwargs['update']
        self._allowed_get_endpoints = ['fftSizes', 'fftSize', 'fftWindows', 'fftWindow']
        self._allowed_put_endpoints = ['fftSize', 'fftWindow']

    def get(self, thing):
        if thing in self._allowed_get_endpoints:
            return jsonify({thing: self._status[thing]})
        return f"Endpoint {thing} not supported", 403

    def put(self, thing):
        if thing in self._allowed_put_endpoints:
            try:
                if thing == 'fftSize':
                    size = int(request.json[thing])
                    if size in self._status['fftSizes']:
                        self._update[thing] = size
                    else:
                        raise ValueError()
                elif thing == 'fftWindow':
                    wnd = request.json[thing]
                    if wnd in self._status['fftWindows']:
                        self._update[thing] = wnd
                    else:
                        raise ValueError()
                return "ok"
            except Exception:
                return "Failed to parse {thing} endpoint", 400
        return f"Endpoint {thing} not supported", 403


class Control(Resource):
    # Handle all web requests on the /control endpoint

    def __init__(self, **kwargs):
        # set the dictionary we use for updating things
        self._status = kwargs['status']
        self._update = kwargs['update']
        self._allowed_get_endpoints = ['presetFps', 'fps', 'stop', 'fpsMeasured', 'delay', 'readRatio', 'headroom',
                                       'overflows', 'oneInN']
        self._allowed_put_endpoints = ['ackTime', 'fps', 'stop']

    def get(self, thing):
        if thing in self._allowed_get_endpoints:
            return jsonify({thing: self._status[thing]})
        return f"Endpoint {thing} not supported", 403

    def put(self, thing):
        if thing in self._allowed_put_endpoints:
            try:
                if thing == 'ackTime':
                    self._update[thing] = request.json[thing]
                elif thing == 'fps':
                    set_fps = abs(int(request.json[thing]['set']))
                    measured = self._status['fps']['measured']
                    self._update[thing] = {'set': set_fps, 'measured': measured}
                elif thing == 'stop':
                    self._update[thing] = request.json[thing]
                return "ok"
            except Exception:
                return "Failed to parse {thing} command", 400
        return f"Endpoint {thing} not supported", 403


class Snapshot(Resource):
    # Handle all web requests on the /snapshot endpoint

    def __init__(self, **kwargs):
        # set the dictionary we use for updating things
        self._status = kwargs['status']
        self._update = kwargs['update']
        self._allowed_get_endpoints = ['snapTriggerSources', 'snapTriggerSource', 'snapTriggerState',
                                       'snapName', 'snapFormats', 'snapFormat', 'snapPreTrigger', 'snapPostTrigger',
                                       'snapSize', 'snaps']
        self._allowed_put_endpoints = ['snapTrigger', 'snapTriggerSource', 'snapName', 'snapFormat',
                                       'snapPreTrigger', 'snapPostTrigger']
        self._allowed_delete_endpoints = ['snapDelete']

    def get(self, thing):
        if thing in self._allowed_get_endpoints:
            return jsonify({thing: self._status[thing]})
        return f"Endpoint {thing} not supported", 403

    def put(self, thing):
        if thing in self._allowed_put_endpoints:
            try:
                if thing == 'snapTrigger':
                    self._update[thing] = request.json[thing]
                elif thing == 'snapTriggerSource':
                    src = request.json[thing]
                    if src in self._status['snapTriggerSources']:
                        self._update[thing] = src
                    else:
                        raise ValueError()
                elif thing == 'snapName':
                    nme = request.json[thing]
                    if len(nme) > 0:
                        self._update[thing] = nme
                    else:
                        raise ValueError()
                elif thing == 'snapFormat':
                    frm = request.json[thing]
                    if frm in self._status['snapFormats']:
                        self._update[thing] = frm
                    else:
                        raise ValueError()
                elif thing == 'snapPreTrigger':
                    pre = abs(int(request.json[thing]))
                    self._update[thing] = pre
                elif thing == 'snapPostTrigger':
                    pos = abs(int(request.json[thing]))
                    self._update[thing] = pos
                return "ok"
            except Exception:
                return "Failed to parse {thing} command", 400
        return f"Endpoint {thing} not supported", 403

    def delete(self, thing):
        if thing in self._allowed_delete_endpoints:
            if thing == 'snapDelete':
                self._update[thing] = request.json[thing]
            return f"deleting {request.json[thing]}"
        return f"Endpoint {thing} not supported", 403


class Tuning(Resource):
    # Handle all web requests on the /tuning endpoint
    def __init__(self, **kwargs):
        # set the dictionary we use for updating things
        self._status = kwargs['status']
        self._update = kwargs['update']
        self._allowed_get_endpoints = ['frequency']
        self._allowed_put_endpoints = ['frequency']

    def get(self, thing):
        if thing in self._allowed_get_endpoints:
            return jsonify({thing: self._status[thing]})
        return f"Endpoint {thing} not supported", 403

    def put(self, thing):
        if thing in self._allowed_put_endpoints:
            try:
                if thing == 'frequency':
                    f = abs(int(request.json['value']))
                    c = int(request.json['conversion'])
                    self._update[thing] = {'value': f, 'conversion': c}
                return "ok"
            except Exception as err:
                return f"Failed to parse {thing} command", 400
        return f"Endpoint {thing} not supported", 403
