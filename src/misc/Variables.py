"""
Class to hold all the programmes variables that we need to pass around

Used because we seem to need a lot of these in different places during initialisation
"""

import json


class Variables():
    def __init__(self):
        # input data related
        self.fft_size = 2048  # default, but any integer allowed
        self.sample_rate = 1e6  # default
        self.centre_frequency_hz = 433.92e6  # default
        self.sample_types = []
        self.sample_type = '16tbe'  # default Format of sample data

        # display
        self.fps = 20
        self.measured_fps = 20
        self.oneInN = int(self.sample_rate / (self.fps * self.fft_size))
        self.update_count = 0
        self.stop = True
        self.web_port = 8080

        # where the data comes from
        self.input_source = "?"  # the source type e.g. file, socket, pluto, soapy, rtlsdr, audio ....
        self.input_params = ""  # the parameters for the source, e.g. filename or ip address ...
        self.source_sleep = 0.01  # only used in file input for now, slows things down
        self.time_first_spectrum: float = 0

        # List of data source
        self.input_sources = []
        self.input_sources_web_helps = []

        # List of plugin options, --plugin xyz:abc:def
        self.plugin_options = []

        self.error = ""

    def make_json(self):
        return json.dumps(self, default=lambda o: o.__dict__)