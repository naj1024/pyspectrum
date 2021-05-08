"""
Class to hold all the programmes variables that we need to pass around

Used because we seem to need a lot of these in different places during initialisation

Passed to the UI as a jason string every few seconds
"""

import json


class SdrVariables:
    def __init__(self):
        self.type = "control"  # for use by javascript to distinguish control types

        self.uuid = 0  # for UI to tag state so it can tell if it gets back state correctly

        # input data related
        self.fft_size = 2048  # default, but any integer allowed
        self.window = ""
        self.window_types = []

        self.sample_rate = 1e6  # default
        self.centre_frequency_hz = 433.92e6  # used by the sdr
        self.conversion_frequency_hz = 0.0
        self.real_centre_frequency_hz = self.centre_frequency_hz  # takes account of any offset, readonly here
        self.sample_types = []
        self.sample_type = '16tbe'  # default Format of sample data
        self.gain = 0
        self.gain_modes = []
        self.gain_mode = ""
        self.input_bw_hz = self.sample_rate
        self.ppm_error = 0.0
        self.read_ratio = 0.0  # ratio of time it takes to read samples vs time samples should of taken to arrive
        # >1.0 means that samples are not arriving at the rate we expect
        self.headroom = 0.0  # % processing time left

        # display
        self.fps = 20
        self.update_count = 0
        self.measured_fps = 20
        self.time_measure_fps = 0
        self.sent_count = 0
        self.stop = False
        self.web_port = 8080
        self.ack = 0  # time in seconds of the last data displayed by the UI, updated by UI
        self.ui_delay = 0  # measured difference between now and ack from ui

        # where the data comes from
        self.input_source = "null"  # the source type e.g. file, socket, pluto, soapy, rtlsdr, audio ....
        self.input_params = ""  # the parameters for the source, e.g. filename or ip address ...
        self.time_first_spectrum: float = 0
        self.source_connected = False

        # List of data source, discovered by looking in dataSources directory
        self.input_sources = []
        self.input_sources_web_helps = []

        # List of plugin options, discovered by looking in plugins directory
        #   --plugin xyz:abc:def
        self.plugin_options = []

        self.error = ""  # any errors we want to have available in the UI

    def make_json(self):
        return json.dumps(self, default=lambda o: o.__dict__)


def add_to_error(config: SdrVariables, err: str) -> None:
    if len(err) != 0:
        config.error += f"{err}\n"
