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
                flask_app.run(host="0.0.0.0", port=self._port, debug=False, use_reloader=False, threaded=False)
            except KeyboardInterrupt:
                logger.info("FlaskInterface received Ctrl+C, shutting down")
                self._shutdown = True
            except Exception as msg:
                logger.error(f"FlaskServer {msg}")
                time.sleep(1)

        logger.error("WebServer process exited")
        return

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
        return {
            ep: self._status.get(ep, "tbd")
            for ep in self._allowed_get_endpoints
        }

    def get(self, thing):
        if thing == "api":
            return jsonify({"input": self.api()})

        if thing not in self._allowed_get_endpoints:
            return f"Endpoint {thing} not supported", 403

        if thing == "errors":
            tmp = self._status.get("errors", "")
            self._status["errors"] = ""
            return jsonify({"errors": tmp})

        return jsonify({thing: self._status.get(thing)})

    def put(self, thing):
        if thing not in self._allowed_put_endpoints:
            return f"Endpoint {thing} not supported", 403

        if thing == 'source':
            data = request.get_json(silent=True) or {}
            s = data.get('source')
            p = data.get('params')

            if s is None or p is None:
                return f"Missing 'source' or 'params'", 400

            self._updateQ.put({
                "type": thing,
                "set": s,
                "params": p,
                "connected": "false",
            })
            return "ok"


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
        return {
            ep: self._status.get(ep, "tbd")
            for ep in self._allowed_get_endpoints
        }

    def get(self, thing):
        if thing == "api":
            return jsonify({"digitiser": self.api()})

        if thing in self._allowed_get_endpoints:
            value = self._status.get(thing)
            if value is None:
                logger.error(f"Missing key in status: {thing}")
                return f"Status for {thing} not available", 404

            return jsonify({thing: value})

        return f"Endpoint {thing} not supported", 403

    def put(self, thing):
        if thing not in self._allowed_put_endpoints:
            return f"Endpoint {thing} not supported", 403

        data = request.get_json(silent=True) or {}

        if thing not in data:
            return f"Missing '{thing}'", 400

        value = data[thing]

        try:
            if thing == 'digitiserFormat':
                if value not in self._status.get('digitiserFormats', []):
                    return "Invalid digitiserFormat", 400
                payload = value

            elif thing == 'digitiserSampleRate':
                payload = abs(int(value))

            elif thing == 'digitiserBandwidth':
                payload = float(value)

            elif thing == 'digitiserPartsPerMillion':
                payload = float(value)

            elif thing == 'digitiserDbmOffset':
                payload = float(value)

            elif thing == 'digitiserGainType':
                if value not in self._status.get('digitiserGainTypes', []):
                    return "Invalid digitiserGainType", 400
                payload = value

            elif thing == 'digitiserDcRemoval':
                if value not in self._status.get('digitiserDcRemovals', []):
                    return "Invalid digitiserDcRemoval", 400
                payload = value

            elif thing == 'digitiserGain':
                payload = int(value)

            elif thing == 'readMagnitudes':
                payload = value

            else:
                return f"Unhandled endpoint {thing}", 500  # safety fallback

        except (TypeError, ValueError):
            return f"Invalid value for {thing}", 400

        self._updateQ.put({
            "type": thing,
            "set": payload,
        })

        return "ok"


class Spectrum(Resource):
    # Handle all web requests on the /spectrum endpoint
    def __init__(self, **kwargs):
        # set the dictionary we use for updating things
        self._status = kwargs['status']
        self._updateQ = kwargs['updateQ']
        self._allowed_get_endpoints = ['fftSizes', 'fftSize', 'psd', 'peakDetect', 'fftOverlap', 'fftOverlaps',
                                       'fftFrameTime', 'fftWindows', 'fftWindow', 'fftRbw']
        self._allowed_put_endpoints = ['fftSize', 'fftOverlap', 'psd', 'peakDetect', 'fftWindow']

    def api(self):
        return {
            ep: self._status.get(ep, "tbd")
            for ep in self._allowed_get_endpoints
        }

    def get(self, thing):
        if thing == "api":
            return jsonify({"spectrum": self.api()})

        if thing in self._allowed_get_endpoints:
            value = self._status.get(thing)
            if value is None:
                logger.error(f"Missing key in status: {thing}")
                return f"Status for {thing} not available", 404

            return jsonify({thing: value})

        return f"Endpoint {thing} not supported", 403

    def put(self, thing):
        if thing not in self._allowed_put_endpoints:
            return f"Endpoint {thing} not supported", 403

        data = request.get_json(silent=True) or {}

        if thing not in data:
            return f"Missing '{thing}'", 400

        value = data[thing]

        try:
            if thing == 'fftSize':
                size = int(value)
                if size not in self._status.get('fftSizes', []):
                    return "Invalid fftSize", 400
                payload = size

            elif thing == 'fftOverlap':
                overlap = int(value)
                if not (0 <= overlap <= 100):
                    return "fftOverlap must be 0–100", 400
                payload = overlap

            elif thing == 'psd':
                payload = value

            elif thing == 'peakDetect':
                payload = value

            elif thing == 'fftWindow':
                if value not in self._status.get('fftWindows', []):
                    return "Invalid fftWindow", 400
                payload = value

            else:
                return f"Unhandled endpoint {thing}", 500  # safety guard

        except (TypeError, ValueError):
            return f"Invalid value for {thing}", 400

        self._updateQ.put({
            "type": thing,
            "set": payload,
        })

        return "ok"


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
        return {
            ep: self._status.get(ep, "tbd")
            for ep in self._allowed_get_endpoints
        }

    def get(self, thing):
        if thing == "api":
            return jsonify({"control": self.api()})

        if thing in self._allowed_get_endpoints:
            value = self._status.get(thing)
            if value is None:
                logger.error(f"Missing key in status: {thing}")
                return f"Status for {thing} not available", 404

            return jsonify({thing: value})

        return f"Endpoint {thing} not supported", 403

    def put(self, thing):
        if thing not in self._allowed_put_endpoints:
            return f"Endpoint {thing} not supported", 403

        data = request.get_json(silent=True) or {}

        if thing == 'ackTime':
            if thing not in data:
                return f"Missing '{thing}'", 400

            self._updateQ.put({
                "type": thing,
                "set": data[thing],
            })

        elif thing == 'fps':
            try:
                set_fps = abs(int(data.get(thing, {}).get('set')))
            except (TypeError, ValueError):
                return "Invalid fps value", 400

            measured = self._status.get('fps', {}).get('measured')

            self._updateQ.put({
                "type": thing,
                "set": set_fps,
                "measured": measured,
            })

        elif thing == 'stop':
            if thing not in data:
                return "Missing stop value", 400

            self._updateQ.put({
                "type": thing,
                "set": data[thing],
            })

        return "ok"

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
        return {
            ep: self._status.get(ep, "tbd")
            for ep in self._allowed_get_endpoints
        }

    def get(self, thing):
        if thing == "api":
            return jsonify({"snapshot": self.api()})

        if thing in self._allowed_get_endpoints:
            value = self._status.get(thing)
            if value is None:
                logger.error(f"Missing key in status: {thing}")
                return f"Status for {thing} not available", 404

            return jsonify({thing: value})

        return f"Endpoint {thing} not supported", 403

    def put(self, thing):
        if thing not in self._allowed_put_endpoints:
            return f"Endpoint {thing} not supported", 403

        data = request.get_json(silent=True) or {}

        try:
            if thing == 'snapTrigger':
                payload = "true"

            elif thing == 'snapTriggerSource':
                value = data.get(thing)
                if value not in self._status.get('snapTriggerSources', []):
                    return "Invalid snapTriggerSource", 400
                payload = value

            elif thing == 'snapName':
                value = data.get(thing)
                if not value:
                    return "snapName cannot be empty", 400
                payload = value

            elif thing == 'snapFormat':
                value = data.get(thing)
                if value not in self._status.get('snapFormats', []):
                    return "Invalid snapFormat", 400
                payload = value

            elif thing == 'snapPreTrigger':
                payload = abs(int(data.get(thing)))

            elif thing == 'snapPostTrigger':
                payload = abs(int(data.get(thing)))

            else:
                return f"Unhandled endpoint {thing}", 500

        except (TypeError, ValueError):
            return f"Invalid value for {thing}", 400

        self._updateQ.put({
            "type": thing,
            "set": payload,
        })

        return "ok"

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
        return {
            ep: self._status.get(ep, "tbd")
            for ep in self._allowed_get_endpoints
        }

    def get(self, thing):
        if thing == "api":
            return jsonify({"tuning": self.api()})

        if thing in self._allowed_get_endpoints:
            value = self._status.get(thing)
            if value is None:
                logger.error(f"Missing key in status: {thing}")
                return f"Status for {thing} not available", 404

            return jsonify({thing: value})

        return f"Endpoint {thing} not supported", 403

    def put(self, thing):
        if thing not in self._allowed_put_endpoints:
            return f"Endpoint {thing} not supported", 403

        data = request.get_json(silent=True) or {} # {'conversion':0, 'value': 1000000}
        try:
            if thing == 'frequency':
                payload = data
            else:
                return f"Unhandled endpoint {thing}", 500

        except (TypeError, ValueError):
            return f"Invalid value for {thing}", 400

        self._updateQ.put({
            "type": thing,
            "set": payload,
        })

        return "ok"


class Status(Resource):
    # Handle all web requests on the /status endpoint

    def __init__(self, **kwargs):
        # set the dictionary we use for updating things
        self._status = kwargs['status']
        self._updateQ = kwargs['updateQ']
        self._allowed_get_endpoints = ['fastStatus', 'currentStatus']
        self._allowed_put_endpoints = []

    def api(self):
        return {
            ep: self._status.get(ep, "tbd")
            for ep in self._allowed_get_endpoints
        }

    def get(self, thing):
        if thing == "api":
            return jsonify({"fastStatus": self.api()})

        if thing not in self._allowed_get_endpoints:
            return f"Endpoint {thing} not supported", 403

        if thing == 'fastStatus':
            stats = [
                'delay', 'loopCpuPc', 'maxCpuCorePc', 'overflows', 'fps', 'oneInN',
                'expectedOneInN', 'digitiserInputLevel', 'digitiserGain',
                'streamLength', 'streamCurrent', 'snapSize', 'snapTriggerState',
            ]
        elif thing == 'currentStatus':
            stats = [
                'source', 'frequency',
                'digitiserFrequency', 'digitiserFormat', 'digitiserSampleRate',
                'digitiserBandwidth', 'digitiserPartsPerMillion', 'digitiserDcRemoval',
                'digitiserInputLevel', 'digitiserDbmOffset', 'digitiserGainType',
                'fftSize', 'fftOverlap', 'psd', 'peakDetect',
                'fftFrameTime', 'fftWindow', 'fftRbw',
                'snapTriggerSource', 'snapName', 'snapFormat',
                'snapPreTrigger', 'snapPostTrigger', 'readMagnitudes'
            ]
        else:
            return f"Unhandled endpoint {thing}", 500

        status = {}
        try:
            for stat in stats:
                status[stat] = self._status.get(stat)  # safe access

            return jsonify({thing: status})

        except BrokenPipeError:
            logger.error(f"Client disconnected for endpoint {thing}")
            return "", 499

        except Exception:
            logger.exception(f"Failed to build response for {thing}")
            return "Internal server error", 500

    def put(self, thing):
        if thing in self._allowed_put_endpoints:
            try:
                return "ok"
            except Exception:
                return f"Failed to parse {thing} command", 400
        return f"Endpoint {thing} not supported", 403
