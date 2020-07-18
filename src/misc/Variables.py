"""
Class to hold all the programmes variables that we need to pass around

Used because we seem to need a lot of these in different places during initialisation
"""


class Variables:
    def __init__(self):
        # input data related
        self.fft_size = 2048  # default, but any integer allowed
        self.sample_rate = 1e6  # default
        self.centre_frequency_hz = 433.92e6  # default
        self.sample_types = ["8t", "16tle", "16tbe"]  # supported sample formats for conversion to complex 32f
        self.sample_type = '16tbe'  # default Format of sample data

        # the spectral matplotlib_ui
        self.spectrogram_flag = False  # default, no spectrogram
        self.spectral_peak_hold = True  # default is to peak hold on spectrums NOT sent to the matplotlib_ui

        # web matplotlib_ui
        self.web_display = False

        # where the data comes from
        self.input_type = "?"  # the source type e.g. file, socket, pluto, soapy, rtlsdr, audio ....
        self.input_name = ""  # the parameters for the source, e.g. filename or ip address ...
        self.source_loop = False  # only meaningful for things that we can loop round on, e.g. file
        self.source_sleep = 0.0  # only used in file input for now, slows things down

        # Misc
        self.alpha_for_ewma = 0.01  # Averaging weight for fft power bins

        # List of plugin options, --plugin xyz:abc:def
        self.plugin_options = []
