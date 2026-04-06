#!/usr/bin/env python3
import logging
import multiprocessing
import os
import pathlib
import signal
import time

from flask import Flask, request, jsonify, send_from_directory
from flask_restful import Resource, Api as Rest_Api

from misc import global_vars
from misc.global_vars import SNAPSHOT_DIRECTORY, THUMBNAILS_DIRECTORY

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
                 update_queue: multiprocessing.Queue):
        """
        Initialise the server

        :param to_ui_queue: we pass it to a web socket server
        :param log_level: The logging level we wish to use
        :param shared_status: A dictionary with current status
        :param update_queue: A queue with the updates from the UI, will only contain updates
        """
        multiprocessing.Process.__init__(self)

        self._status = shared_status
        self._updateQ = update_queue

        # queues are for the web socket, not used in the web server
        self._to_ui_queue = to_ui_queue
        self._port = shared_status['web_server_port']
        print(f"web server port {self._port}")
        self._httpd = None
        self._log_level = log_level
        self._shutdown = False

        # dictionary linking api names to Classes for the main endpoints
        self._endpoints = {'input': Input,
                           'digitiser': Digitiser,
                           'spectrum': Spectrum,
                           'control': Control,
                           'snapshot': Snapshot,
                           'tuning': Tuning,
                           'status': Status}

    def shutdown(self):
        logger.debug("FlaskServer Shutting down")
        self._shutdown = True
        if self._httpd:
            self._httpd.shutdown()
        logger.debug("FlaskServer shutdown")

    def signal_handler(self, _sig, __):
        self.shutdown()

    def run(self):
        """
        Run the web server process
        Also creates the web socket server

        :return: None
        """

        global logger
        log_file = pathlib.PurePath(os.path.dirname(__file__), "..", global_vars.log_dir, __name__ + ".log")

        try:
            file_handler = logging.FileHandler(log_file, mode="w")
        except Exception as msg:
            print(f"Failed to create logger for Flask webserver, {msg}")
            exit(1)

        formatter = logging.Formatter('%(asctime)s,%(levelname)s:%(name)s:%(module)s:%(message)s',
                                      datefmt="%Y-%m-%d %H:%M:%S UTC")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logging.Formatter.converter = time.gmtime
        logger.setLevel(self._log_level)

        logger.info(f"WebSocket starting on port {self._port}")

        # as we are in a separate process the thing that spawned us can't call shutdown correctly
        # It can send us a signal, then we can shut down our self
        signal.signal(signal.SIGINT, self.signal_handler)

        # serve all the pages from the webroot
        flask_app = Flask(__name__,
                          static_url_path='/',
                          static_folder='webroot')

        @flask_app.route('/snapshots/<path:filename>')
        def snapshots(filename):
            return send_from_directory(SNAPSHOT_DIRECTORY, filename)

        @flask_app.route('/thumbnails/<path:filename>')
        def thumbnails(filename):
            return send_from_directory(THUMBNAILS_DIRECTORY, filename)

        # remove all logging from the flask server, removes prints of urls to console
        # enable this if you need to see what is being served
        logw = logging.getLogger('werkzeug')
        logw.disabled = True

        # don't disable the next one as it stops our logging as well
        # flask_app.logger.disabled = True

        rest_api = Rest_Api(flask_app)

        # server the main static web page on empty URL
        @flask_app.route("/", methods=['GET'])
        def index():
            return flask_app.send_static_file('index.html')

        # for Flask associate each endpoint with the class that handles it
        # each endpoint Class handles all the endpoints under it, hence it must have something
        # after the /{entry}/, e.g. /{entry()}/sources but not just /{entry}/
        for entry, c in self._endpoints.items():
            # describe the endpoint
            uri = f"/{entry}/<string:thing>"
            rest_api.add_resource(c,
                                  uri,
                                  resource_class_kwargs={'status': self._status, 'updateQ': self._updateQ})

        # api endpoint is different from all the other ones
        rest_api.add_resource(Api,
                              '/api',
                              resource_class_kwargs={'endpoints': self._endpoints})

        # web_socket_api.route(Websock,
        #                      '/spectrum')

        # serve the content forever
        global web_root
        while not self._shutdown:
            try:
                logger.info(f"flask restful server serving {web_root} on port {self._port}")
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

class Api(Resource):
    # returns one json containing all the first level endpoints we support
    def __init__(self, **kwargs):
        self._eps = kwargs['endpoints']

    def get(self):
        endpoints = ['api']
        for endpoint in self._eps:
            endpoints.append(endpoint)
        return jsonify({"endpoints": endpoints})


class Input(Resource):
    # Handle all web requests on the /input endpoint
    def __init__(self, **kwargs):
        # set the dictionary we use for updating things
        self._status = kwargs['status']
        self._updateQ = kwargs['updateQ']
        self._allowed_get_endpoints = ['sources', 'source', 'errors']
        self._allowed_put_endpoints = ['source']

    def api(self):
        points = {}
        for ep in self._allowed_get_endpoints:
            try:
                points[ep] = self._status[ep]
            except Exception:
                points[ep] = "tbd"  # not present in status yet
        return points

    def get(self, thing):
        if thing == "api":
            return jsonify({"input": self.api()})

        if thing in self._allowed_get_endpoints:
            if thing == "errors":
                tmp = ""
                # error entry may not be present
                if thing in self._status.keys():
                    tmp = self._status[thing]
                    self._status[thing] = ""
                try:
                    return jsonify({thing: tmp})
                except Exception:
                    logger.error(f"Failed to jsonify for {thing} {type(tmp)}")
            else:
                return jsonify({thing: self._status[thing]})
        return f"Endpoint {thing} not supported", 403

    def put(self, thing):
        if thing in self._allowed_put_endpoints:
            if thing == 'source':
                try:
                    s = request.json['source']
                    p = request.json['params']
                    self._updateQ.put({
                        "type": thing,
                        "set": s,
                        "params": p,
                        "connected": "false",
                    })
                except Exception:
                    return f"Failed to parse {thing} endpoint", 400
                return "ok"
        return f"Endpoint {thing} not supported", 403


class Digitiser(Resource):
    # Handle all web requests on the /digitiser endpoint
    def __init__(self, **kwargs):
        # set the dictionary we use for updating things
        self._status = kwargs['status']
        self._updateQ = kwargs['updateQ']
        self._allowed_get_endpoints = ['digitiserFrequency', 'digitiserFormats', 'digitiserFormat',
                                       'digitiserSampleRate',
                                       'digitiserBandwidth', 'digitiserPartsPerMillion', 'digitiserGainTypes',
                                       'digitiserGainType', 'digitiserGain',
                                       'digitiserDcRemoval', 'digitiserDcRemovals',
                                       'digitiserDbmOffset', 'digitiserInputLevel',
                                       'streamLength', 'streamCurrent',
                                       'readMagnitudes']
        self._allowed_put_endpoints = ['digitiserFormat', 'digitiserSampleRate', 'digitiserBandwidth',
                                       'digitiserPartsPerMillion', 'digitiserGainType', 'digitiserGain',
                                       'digitiserDcRemoval', 'digitiserDbmOffset', 'readMagnitudes']

    def api(self):
        points = {}
        for ep in self._allowed_get_endpoints:
            try:
                points[ep] = self._status[ep]
            except Exception:
                points[ep] = "tbd"  # not present in status yet
        return points

    def get(self, thing):
        if thing == "api":
            return jsonify({"digitiser": self.api()})

        # Check for allowed endpoints at this point
        if thing in self._allowed_get_endpoints:
            try:
                return jsonify({thing: self._status[thing]})
            except Exception:
                logger.error(f"Failed to jsonify for {thing} {type(self._status[thing])}")
        return f"Endpoint {thing} not supported", 403

    def put(self, thing):
        if thing in self._allowed_put_endpoints:
            try:
                if thing == 'digitiserFormat':
                    fmt = request.json[thing]
                    if fmt in self._status['digitiserFormats']:
                        self._updateQ.put({
                            "type": thing,
                            "set": fmt,
                        })
                    else:
                        raise ValueError()
                elif thing == 'digitiserSampleRate':
                    # request.form for non json put
                    sps = abs(int(request.json[thing]))
                    self._updateQ.put({
                        "type": thing,
                        "set": sps,
                    })
                elif thing == 'digitiserBandwidth':
                    bw = abs(int(request.json[thing]))
                    self._updateQ.put({
                        "type": thing,
                        "set": bw,
                    })
                elif thing == 'digitiserPartsPerMillion':
                    ppm = float(request.json[thing])
                    self._updateQ.put({
                        "type": thing,
                        "set": ppm,
                    })
                elif thing == 'digitiserDbmOffset':
                    offset = float(request.json[thing])
                    self._updateQ.put({
                        "type": thing,
                        "set": offset,
                    })
                elif thing == 'digitiserGainType':
                    gt = request.json[thing]
                    if gt in self._status['digitiserGainTypes']:
                        self._updateQ.put({
                            "type": thing,
                            "set": gt,
                        })
                    else:
                        raise ValueError()
                elif thing == 'digitiserDcRemoval':
                    dc = request.json[thing]
                    if dc in self._status['digitiserDcRemovals']:
                        self._updateQ.put({
                            "type": thing,
                            "set": dc,
                        })
                    else:
                        raise ValueError()
                elif thing == 'digitiserGain':
                    gn = int(request.json[thing])
                    self._updateQ.put({
                            "type": thing,
                            "set": gn,
                    })
                elif thing == 'readMagnitudes':
                    gt = request.json[thing]
                    self._updateQ.put({
                            "type": thing,
                            "set": gt,
                    })
                return "ok"
            except Exception:
                return "Failed to parse {thing} endpoint", 400
        return f"Endpoint {thing} not supported", 403


class Spectrum(Resource):
    # Handle all web requests on the /spectrum endpoint
    def __init__(self, **kwargs):
        # set the dictionary we use for updating things
        self._status = kwargs['status']
        self._updateQ = kwargs['updateQ']
        self._allowed_get_endpoints = ['fftSizes', 'fftSize', 'psd', 'fftOverlap', 'fftOverlaps',
                                       'fftFrameTime', 'fftWindows', 'fftWindow', 'fftRbw']
        self._allowed_put_endpoints = ['fftSize', 'fftOverlap', 'psd', 'fftWindow']

    def api(self):
        points = {}
        for ep in self._allowed_get_endpoints:
            try:
                points[ep] = self._status[ep]
            except Exception:
                points[ep] = "tbd"  # not present in status yet
        return points

    def get(self, thing):
        if thing == "api":
            return jsonify({"spectrum": self.api()})

        if thing in self._allowed_get_endpoints:
            try:
                return jsonify({thing: self._status[thing]})
            except Exception:
                logger.error(f"Failed to jsonify for {thing} {type(self._status[thing])}")
        return f"Endpoint {thing} not supported", 403

    def put(self, thing):
        if thing in self._allowed_put_endpoints:
            try:
                if thing == 'fftSize':
                    size = int(request.json[thing])
                    if size in self._status['fftSizes']:
                        self._updateQ.put({
                            "type": thing,
                            "set": size,
                        })
                    else:
                        raise ValueError()
                elif thing == 'fftOverlap':
                    overlap = int(request.json[thing])
                    if (overlap >= 0) and (overlap <= 100):
                        self._updateQ.put({
                            "type": thing,
                            "set": overlap,
                        })
                    else:
                        raise ValueError()
                elif thing == 'psd':
                    psd = request.json[thing]
                    self._updateQ.put({
                        "type": thing,
                        "set": psd,
                    })
                elif thing == 'fftWindow':
                    wnd = request.json[thing]
                    if wnd in self._status['fftWindows']:
                        self._updateQ.put({
                            "type": thing,
                            "set": wnd,
                        })
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
        self._updateQ = kwargs['updateQ']
        self._allowed_get_endpoints = ['presetFps', 'fps', 'stop', 'fpsMeasured', 'delay', 'loopCpuPc',
                                       'overflows', 'oneInN']
        self._allowed_put_endpoints = ['ackTime', 'fps', 'stop']

    def api(self):
        points = {}
        for ep in self._allowed_get_endpoints:
            try:
                points[ep] = self._status[ep]
            except Exception:
                points[ep] = "tbd"  # not present in status yet
        return points

    def get(self, thing):
        if thing == "api":
            return jsonify({"control": self.api()})

        if thing in self._allowed_get_endpoints:
            try:
                return jsonify({thing: self._status[thing]})
            except Exception:
                logger.error(f"Failed to jsonify for {thing} {type(self._status[thing])}")
        return f"Endpoint {thing} not supported", 403

    def put(self, thing):
        if thing in self._allowed_put_endpoints:
            try:
                if thing == 'ackTime':
                    self._updateQ.put({
                        "type": thing,
                        "set": request.json[thing],
                    })
                elif thing == 'fps':
                    set_fps = abs(int(request.json[thing]['set']))
                    measured = self._status['fps']['measured']
                    self._updateQ.put({
                        "type": thing,
                        "set": set_fps,
                        "measured": measured,
                    })
                elif thing == 'stop':
                    self._updateQ.put({
                        "type": thing,
                        "set": request.json[thing],
                    })
                return "ok"
            except Exception:
                return "Failed to parse {thing} command", 400
        return f"Endpoint {thing} not supported", 403


class Snapshot(Resource):
    # Handle all web requests on the /snapshot endpoint

    def __init__(self, **kwargs):
        # set the dictionary we use for updating things
        self._status = kwargs['status']
        self._updateQ = kwargs['updateQ']
        self._allowed_get_endpoints = ['snapTriggerSources', 'snapTriggerSource', 'snapTriggerState',
                                       'snapName', 'snapFormats', 'snapFormat', 'snapPreTrigger', 'snapPostTrigger',
                                       'snapSize', 'snaps']
        self._allowed_put_endpoints = ['snapTrigger', 'snapTriggerSource', 'snapName', 'snapFormat',
                                       'snapPreTrigger', 'snapPostTrigger']
        self._allowed_delete_endpoints = ['snapDelete']

    def api(self):
        points = {}
        for ep in self._allowed_get_endpoints:
            try:
                points[ep] = self._status[ep]
            except Exception:
                points[ep] = "tbd"  # not present in status yet
        return points

    def get(self, thing):
        if thing == "api":
            return jsonify({"snapshot": self.api()})

        if thing in self._allowed_get_endpoints:
            try:
                return jsonify({thing: self._status[thing]})
            except Exception:
                logger.error(f"Failed to jsonify for {thing} {type(self._status[thing])}")
        return f"Endpoint {thing} not supported", 403

    def put(self, thing):
        if thing in self._allowed_put_endpoints:
            try:
                if thing == 'snapTrigger':
                    self._updateQ.put({
                        "type": thing,
                        "set": "true",
                    })
                elif thing == 'snapTriggerSource':
                    src = request.json[thing]
                    if src in self._status['snapTriggerSources']:
                        self._updateQ.put({
                            "type": thing,
                            "set": src,
                        })
                    else:
                        raise ValueError()
                elif thing == 'snapName':
                    nme = request.json[thing]
                    if len(nme) > 0:
                        self._updateQ.put({
                            "type": thing,
                            "set": nme,
                        })
                    else:
                        raise ValueError()
                elif thing == 'snapFormat':
                    frm = request.json[thing]
                    if frm in self._status['snapFormats']:
                        self._updateQ.put({
                            "type": thing,
                            "set": frm,
                        })
                    else:
                        raise ValueError()
                elif thing == 'snapPreTrigger':
                    pre = abs(int(request.json[thing]))
                    self._updateQ.put({
                        "type": thing,
                        "set": pre,
                    })
                elif thing == 'snapPostTrigger':
                    pos = abs(int(request.json[thing]))
                    self._updateQ.put({
                        "type": thing,
                        "set": pos,
                    })
                return "ok"
            except Exception:
                return "Failed to parse {thing} command", 400
        return f"Endpoint {thing} not supported", 403

    def delete(self, thing):
        if thing in self._allowed_delete_endpoints:
            if thing == 'snapDelete':
                self._updateQ.put({
                    "type": thing,
                    "set": request.json[thing],
                })
            return f"deleting {request.json[thing]}"
        return f"Endpoint {thing} not supported", 403


class Tuning(Resource):
    # Handle all web requests on the /tuning endpoint
    def __init__(self, **kwargs):
        # set the dictionary we use for updating things
        self._status = kwargs['status']
        self._updateQ = kwargs['updateQ']
        self._allowed_get_endpoints = ['frequency']
        self._allowed_put_endpoints = ['frequency']

    def api(self):
        points = {}
        for ep in self._allowed_get_endpoints:
            try:
                points[ep] = self._status[ep]
            except Exception:
                points[ep] = "tbd"  # not present in status yet
        return points

    def get(self, thing):
        if thing == "api":
            return jsonify({"tuning": self.api()})

        if thing in self._allowed_get_endpoints:
            try:
                return jsonify({thing: self._status[thing]})
            except Exception:
                logger.error(f"Failed to jsonify for {thing} {type(self._status[thing])}")
        return f"Endpoint {thing} not supported", 403

    def put(self, thing):
        if thing in self._allowed_put_endpoints:
            try:
                if thing == 'frequency':
                    f = abs(int(request.json['value']))
                    c = int(request.json['conversion'])
                    self._updateQ.put({
                        "type": thing,
                        "set": f,
                        "conversion": c,
                    })
                return "ok"
            except Exception:
                return f"Failed to parse {thing} command", 400
        return f"Endpoint {thing} not supported", 403


class Status(Resource):
    # Handle all web requests on the /status endpoint

    def __init__(self, **kwargs):
        # set the dictionary we use for updating things
        self._status = kwargs['status']
        self._updateQ = kwargs['updateQ']
        self._allowed_get_endpoints = ['fastStatus', 'currentStatus']
        self._allowed_put_endpoints = []

    def api(self):
        points = {}
        for ep in self._allowed_get_endpoints:
            try:
                points[ep] = self._status[ep]
            except Exception:
                points[ep] = "tbd"  # not present in status yet
        return points

    def get(self, thing):
        if thing == "api":
            return jsonify({"fastStatus": self.api()})

        if thing in self._allowed_get_endpoints:
            try:
                if thing == 'fastStatus':
                    stats = ['delay', 'loopCpuPc', 'maxCpuCorePc', 'overflows', 'fps', 'oneInN',
                            'digitiserInputLevel', 'digitiserGain', 'streamLength', 'streamCurrent',
                            'snapSize', 'snapTriggerState',
                            ]
                    status = {}
                    for stat in stats:
                       status[stat] = self._status[stat]
                    return jsonify(status)

                elif thing == 'currentStatus':
                    stats = ['source',
                             'frequency',
                             'digitiserFrequency', 'digitiserFormat', 'digitiserSampleRate',
                             'digitiserBandwidth', 'digitiserPartsPerMillion', 'digitiserDcRemoval',
                             'digitiserInputLevel', 'digitiserDbmOffset', 'digitiserGainType',
                             'fftSize', 'fftOverlap', 'psd', 'fftFrameTime', 'fftWindow', 'fftRbw',
                             'snapTriggerSource', 'snapName', 'snapFormat',
                             'snapPreTrigger', 'snapPostTrigger', 'readMagnitudes'
                            ]
                    status = {}
                    for stat in stats:
                       status[stat] = self._status[stat]
                    return jsonify(status)
            except Exception:
                logger.error(f"Failed to jsonify for {thing} {type(self._status[thing])}")
        return f"Endpoint {thing} not supported", 403

    def put(self, thing):
        if thing in self._allowed_put_endpoints:
            try:
                return "ok"
            except Exception:
                return f"Failed to parse {thing} command", 400
        return f"Endpoint {thing} not supported", 403
