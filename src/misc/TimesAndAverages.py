"""
Class to timings and averages

"""
from misc import Ewma


class TimesAndAverages:
    def __init__(self):
        self.loop_time = Ewma.Ewma(0.001)
        self.cpu_core = Ewma.Ewma(0.01)
        self.effective_sps = Ewma.Ewma(0.01)

        self.source_stats_time = 0  # when we will send our config to the UI
        self.fps_update_time = 0
