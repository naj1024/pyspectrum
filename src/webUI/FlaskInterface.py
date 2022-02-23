#!/usr/bin/env python3
import logging
import multiprocessing
import os
import pathlib
import signal
import time

from flask import Flask, request, jsonify
from flask_restful import Resource, Api

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
                 web_port: int,
                 config: dict):
        """
        Initialise the server

        :param to_ui_queue: we pass it to a web socket server
        :param log_level: The logging level we wish to use
        :param web_port: The port the web server will serve on
        """
        multiprocessing.Process.__init__(self)

        self._config = config

        # queues are for the web socket, not used in the web server
        self._to_ui_queue = to_ui_queue
        self._port = web_port
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
        # but it can send us a signal, then we can shutdown our self
        signal.signal(signal.SIGINT, self.signal_handler)

        # serve all the pages from the webroot
        flask_app = Flask(__name__,
                          static_url_path='/',
                          static_folder='webroot')

        # remove all logging from the flask server, removes prints of urls to console
        logw = logging.getLogger('werkzeug')
        logw.disabled = True
        flask_app.logger.disabled = True

        api = Api(flask_app)

        # server the main static web page on empty URL
        @flask_app.route("/", methods=['GET'])
        def index():
            return flask_app.send_static_file('index.html')

        api.add_resource(Input, '/input/<string:thing>', resource_class_kwargs={'config': self._config})
        api.add_resource(Digitiser, '/digitiser/<string:thing>', resource_class_kwargs={'config': self._config})
        api.add_resource(Spectrum, '/spectrum/<string:thing>', resource_class_kwargs={'config': self._config})
        api.add_resource(Control, '/control/<string:thing>', resource_class_kwargs={'config': self._config})
        api.add_resource(Snapshot, '/snapshot/<string:thing>', resource_class_kwargs={'config': self._config})
        api.add_resource(Tuning, '/tuning/<string:thing>', resource_class_kwargs={'config': self._config})

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
        self._config = kwargs['config']

    def get(self, thing):
        try:
            # note that we can pick up entries that are not at our endpoint
            # e.g. /digitiser/frequency will return the tuning/frequency
            # there is no /digitiser/frequency
            # this is because we are mapping direct into the dictionary
            # so check for allowed endpoints at this point
            allowed = ['sources', 'source']
            if thing in allowed:
                return jsonify({thing: self._config[thing]})
        except KeyError:
            pass
        return "Endpoint problem", 403

    def put(self, thing):
        try:
            if thing == 'source':
                s = request.json['source']
                p = request.json['params']
                self._config[thing] = {'source': s, 'params': p, 'connected': False}
                return "ok"
            else:
                pass
        except (KeyError, ValueError):
            pass
        return "Endpoint problem", 403


class Digitiser(Resource):
    # Handle all web requests on the /digitiser endpoint
    def __init__(self, **kwargs):
        # set the dictionary we use for updating things
        self._config = kwargs['config']

    def get(self, thing):
        try:
            allowed = ['digitiserFrequency', 'digitiserFormats', 'digitiserFormat', 'digitiserSampleRate',
                       'digitiserBandwidth', 'digitiserPartsPerMillion', 'digitiserGainTypes', 'digitiserGainType',
                       'digitiserGain']
            if thing in allowed:
                return jsonify({thing: self._config[thing]})
        except KeyError:
            pass
        return "Endpoint problem", 403

    def put(self, thing):
        try:
            if thing == 'digitiserFormat':
                fmt = request.json[thing]
                if fmt in self._config['digitiserFormats']:
                    self._config[thing] = fmt
                    return "ok"
            elif thing == 'digitiserSampleRate':
                # request.form for non json put
                sps = abs(int(request.json[thing]))
                self._config[thing] = sps
                return "ok"
            elif thing == 'digitiserBandwidth':
                bw = abs(int(request.json[thing]))
                self._config[thing] = bw
                return "ok"
            elif thing == 'digitiserPartsPerMillion':
                ppm = float(request.json[thing])
                self._config[thing] = ppm
                return "ok"
            elif thing == 'digitiserGainType':
                gt = request.json[thing]
                if gt in self._config['digitiserGainTypes']:
                    self._config[thing] = gt
                    return "ok"
            elif thing == 'digitiserGain':
                gn = abs(int(request.json[thing]))
                self._config[thing] = gn
                return "ok"
        except (KeyError, ValueError):
            pass
        return "Endpoint problem", 403


class Spectrum(Resource):
    # Handle all web requests on the /spectrum endpoint
    def __init__(self, **kwargs):
        # set the dictionary we use for updating things
        self._config = kwargs['config']

    def get(self, thing):
        try:
            allowed = ['fftSizes', 'fftSize', 'fftWindows', 'fftWindow']
            if thing in allowed:
                return jsonify({thing: self._config[thing]})
        except KeyError:
            pass
        return "Endpoint problem", 403

    def put(self, thing):
        try:
            if thing == 'fftSize':
                size = int(request.json[thing])
                if size in self._config['fftSizes']:
                    self._config[thing] = size
                    return "ok"
            elif thing == 'fftWindow':
                wnd = request.json[thing]
                if wnd in self._config['fftWindows']:
                    self._config[thing] = wnd
                    return "ok"
        except (KeyError, ValueError):
            pass
        return "Endpoint problem", 403


class Control(Resource):
    # Handle all web requests on the /control endpoint

    def __init__(self, **kwargs):
        # set the dictionary we use for updating things
        self._config = kwargs['config']

    def get(self, thing):
        try:
            allowed = ['presetFps', 'fps', 'stop', 'fpsMeasured', 'delay', 'readRatio', 'headroom', 'overflows', 'oneInN']
            if thing in allowed:
                return jsonify({thing: self._config[thing]})
        except KeyError:
            pass
        return "Endpoint problem", 403

    def put(self, thing):
        try:
            if thing == 'stop':
                self._config[thing] = request.json[thing]
            if thing == 'fps':
                set = abs(int(request.json[thing]['set']))
                measured = self._config['fps']['measured']
                self._config[thing] = {'set': set, 'measured': measured}
                return "ok"
            elif thing == 'ackTime':
                self._config[thing] = request.json[thing]
                return "ok"
            elif thing == 'stop':
                self._config[thing] = request.json[thing]
                return "ok"
        except (KeyError, ValueError):
            pass
        return "Endpoint problem", 403


class Snapshot(Resource):
    # Handle all web requests on the /snapshot endpoint

    def __init__(self, **kwargs):
        # set the dictionary we use for updating things
        self._config = kwargs['config']

    def get(self, thing):
        try:
            allowed = ['snapTriggerSources', 'snapTriggerSource', 'snapTriggerState',
                       'snapName', 'snapFormats', 'snapFormat', 'snapPreTrigger', 'snapPostTrigger',
                       'snapSize', 'snaps']
            if thing in allowed:
                return jsonify({thing: self._config[thing]})
        except KeyError:
            pass
        return "Endpoint problem", 403

    def put(self, thing):
        try:
            if thing == 'snapTrigger':
                self._config[thing] = request.json[thing]
                return "ok"
            elif thing == 'snapTriggerSource':
                src = request.json[thing]
                if src in self._config['snapTriggerSources']:
                    self._config[thing] = src
                    return "ok"
            elif thing == 'snapName':
                nme = request.json[thing]
                if len(nme) > 0:
                    self._config[thing] = nme
                    return "ok"
            elif thing == 'snapFormat':
                frm = request.json[thing]
                if frm in self._config['snapFormats']:
                    self._config[thing] = frm
                    return "ok"
            elif thing == 'snapPreTrigger':
                pre = abs(int(request.json[thing]))
                self._config[thing] = pre
                return "ok"
            elif thing == 'snapPostTrigger':
                pos = abs(int(request.json[thing]))
                self._config[thing] = pos
                return "ok"
        except (KeyError, ValueError):
            pass
        return "Endpoint problem", 403

    def delete(self, thing):
        try:
            if thing == 'snapDelete':
                self._config[thing] = request.json[thing]
                return "deleted"
            else:
                pass
        except KeyError:
            pass
        return "Endpoint problem", 403


class Tuning(Resource):
    # Handle all web requests on the /tuning endpoint
    def __init__(self, **kwargs):
        # set the dictionary we use for updating things
        self._config = kwargs['config']

    def get(self, thing):
        try:
            allowed = ['frequency']
            if thing in allowed:
                return jsonify({thing: self._config[thing]})
        except KeyError:
            pass
        return "Endpoint problem", 403

    def put(self, thing):
        try:
            if thing == 'frequency':
                f = abs(int(request.json['value']))
                c = abs(int(request.json['conversion']))
                self._config[thing] = {'value': f, 'conversion': c}
                return "ok"
        except (KeyError, ValueError):
            pass
        return "Endpoint problem", 403
