"""
Class to timings and averages

"""
from misc import Ewma


class TimesAndAverages:
    def __init__(self):
        self.capture_time = Ewma.Ewma(0.001)  # soapy is very blocky so different averaging for all
        self.loop_time = Ewma.Ewma(0.01)
        self.process_time = Ewma.Ewma(0.01)
        self.reporting_time = Ewma.Ewma(0.01)
        self.snap_time = Ewma.Ewma(0.01)
        self.ui_time = Ewma.Ewma(0.01)
        self.sync_from_ui = Ewma.Ewma(0.01)
        self.save_samples = Ewma.Ewma(0.01)
        self.dc_offset = Ewma.Ewma(0.01)
        self.plugins = Ewma.Ewma(0.01)
        self.snap_config = Ewma.Ewma(0.01)
        self.misc = Ewma.Ewma(0.01)

        self.config_time = 0  # when we will send our config to the UI
        self.debug_time = 0
        self.fps_update_time = 0
