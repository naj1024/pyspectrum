"""
Class to hold all the programmes variables that we need to pass around

Used because we seem to need a lot of these in different places during initialisation

Passed to the UI as a jason string every few seconds
"""

import json


class Sdr:
    def __init__(self):
        self.sample_rate = 1e6  # default
        self.centre_frequency_hz = 433.92e6  # used by the sdr
        self.conversion_frequency_hz = 0.0
        self.sdr_centre_frequency_hz = self.centre_frequency_hz - self.conversion_frequency_hz
        self.sample_types = ['8o', '8t', '16tbe', '16tle', '32fle', '32fbe']
        self.sample_type = '16tbe'  # default Format of sample data
        self.drop = 0; # drops input buffers, e.g. 1 is drop 1 in 1, 2 is drop 1 in 2, 3 is drop 1 in 3
        self.keep = 1; # keeps input buffers, e.g. 1 is keep every, 2 is keep 1 in 2, 3 is keep 1 in 3
        self.gain = 0
        self.gain_modes = ['none']
        self.gain_mode = "none"
        self.input_bw_hz = self.sample_rate
        self.ppm_error = 0.0
        self.dbm_offset = 0.0

        # input data related
        self.fft_size = 2048  # default, but any integer allowed
        self.fft_frame_time = 1e6 * (self.fft_size / self.sample_rate) # useconds
        self.window = ""
        self.window_types = []

        self.loop_cpu_pc = 0.0  # % of fft/sample rate time being used

        # display
        self.fps = 20
        self.fps_override = False
        self.update_count = 0
        self.measured_fps = 20
        self.time_measure_fps = 0
        self.sent_count = 0
        self.stop = False
        self.web_port = 8080
        self.ackTime = 0  # time in seconds of the last data displayed by the UI, updated by UI
        self.ui_delay = 0  # measured difference between now and ack from ui
        self.one_in_n = 0

        # where the data comes from
        self.input_source = "null"  # the source type e.g. file, socket, pluto, soapy, rtlsdr, audio ....
        self.input_params = ""  # the parameters for the source, e.g. filename or ip address ...
        self.time_first_spectrum: float = 0
        self.source_connected = False
        self.input_overflows = 0

        # List of data source, discovered by looking in dataSources directory
        self.input_sources = []
        self.input_sources_with_helps = []

        # List of plugin options, discovered by looking in plugins directory
        #   --plugin xyz:abc:def
        self.plugin_options = []

        self.error = ""  # any errors we want to have available in the UI


def add_to_error(config: Sdr, err: str) -> None:
    if len(err) != 0:
        config.error += f"{err}\n"


def get_and_reset_error(config: Sdr) -> str:
    tmp = config.error
    config.error = ""
    return tmp
