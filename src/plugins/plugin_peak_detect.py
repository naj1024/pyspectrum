import logging
import textwrap
from typing import List
from typing import Tuple

import numpy as np

from misc.PluginManager import Plugin

logger = logging.getLogger('spectrum_logger')

default_threshold = 100.0  # very large to stop any peak detects unless we use --plugin option
help_string = textwrap.dedent(f'''
              Analysis type plugin. 
                Finds peaks above a threshold from the average noise floor.
                Takes option:
                   --plugin analysis:peak:threshold:10 
                default threshold: {default_threshold}dB''')


class PeakDetect(Plugin):
    def __init__(self, **kwargs):
        # Note we need to have a class method for each entry in the self_methods list
        # and the name has to match
        self._methods = ['analysis']
        self._enabled = False
        self._threshold = default_threshold
        self._help_string = help_string
        self._parse_options(kwargs)

    def _parse_options(self, options: {}) -> None:
        """
        Parse the given dictionary of options to see if there is anything for us
        :param options: Dictionary of stuff, note that these are NOT the command line args but derived from them
        :return: None
        """
        if "plugin_options" in options:
            for opts in options["plugin_options"]:
                if len(opts):
                    opt = opts[0]
                    parts = [x.strip() for x in opt.split(':')]
                    if len(parts) == 4:
                        # --plugin analysis:peak:threshold:10
                        if parts[0] == "analysis" and parts[1] == "peak" and parts[2] == "threshold":
                            self._threshold = float(parts[3])

                        # --plugin analysis:peak:enabled:on
                        if parts[0] == "analysis" and parts[1] == "peak" and parts[2] == "enabled":
                            if parts[3] == "on":
                                self._enabled = True
                            else:
                                self._enabled = False

    def help(self):
        """
        return the help string for this plugin
        :return: The help string, pre-formatted
        """
        return self._help_string

    def analysis(self, powers: np.ndarray, noise_floors: np.ndarray, reordered: bool = False) -> Tuple[str, List[int]]:
        """" Detect all values above the average by threshold

        :param powers: The current spectrum powers in dB from an fft
        :param noise_floors: The average of each bin in dB from an fft
        :param reordered: Has fftshift been used on the array of fft bins, i.e is it:
                          True:-ve,zero,+ve or
                          False:zero,+ve,-ve
        :return: The bin values of the peaks in fftshift order, i.e. 0 is most negative
        """
        if self._enabled:
            # thresholds with the floor and threshold applied
            thresholds = noise_floors + self._threshold
            # find the bin indexes in the powers that are above the thresholds
            peak_bins = np.where(powers > thresholds)
            # put the bins in a list and correct for frequency
            bin_list = peak_bins[0].tolist()
            if not reordered:
                pass
                # we have bins numbered with from [0]=zero to [fft/2-1]=most +ve and [fft/2]=most -ve to [fft]=zero
                # we want [0]=most -ve
                # [fft/2-1]=zero
                # [[fft-1]=most +ve
                half_fft_size = powers.size // 2
                for index, bin_value in enumerate(bin_list):
                    if bin_value < half_fft_size:
                        bin_list[index] = bin_value + half_fft_size
                    else:
                        bin_list[index] = bin_value - half_fft_size
            return "peaks", bin_list
        return "peaks", []
