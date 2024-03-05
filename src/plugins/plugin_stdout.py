import logging
import textwrap
import time
from typing import List

from misc.PluginManager import Plugin

logger = logging.getLogger('spectrum_logger')

help_string = textwrap.dedent(f'''
              Report type plugin. 
                Sends any results to stdout.
                Takes options:
                    --plugin report:stdout:enabled:on
                default enabled:off''')


class Stdout(Plugin):
    def __init__(self, **kwargs):
        # Note we need to have a class method for each entry in the self_methods list
        # and the name has to match
        self._methods = ['report']
        self._enabled = False
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
                    if len(parts) == 3:
                        # --plugin report:stdout:enabled:off
                        if parts[0] == "report" and parts[1] == "stdout" and parts[2] == "enabled":
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

    def report(self, data_samples_time: float,
               frequencies: List[float],
               centre_frequency_hz: float) -> None:
        """
        Print things to stdout

        :param data_samples_time: Time of samples that caused an event in nsec
        :param frequencies: List of frequencies offsets that were found
        :param centre_frequency_hz: The centre frequency for the list of frequency offsets
        :return: None
        """
        if self._enabled:
            secs = int(data_samples_time / 1e9)
            micro_secs = ((data_samples_time / 1e9) - secs) * 1000
            happened_at = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(secs))
            centre_frequencies = [(freq + centre_frequency_hz) / 1e6 for freq in frequencies]
            print(f"{happened_at} + {micro_secs:0.0f}usecs: ", end='')
            for freq in centre_frequencies:
                print(f"{freq:0.3f}MHz, ", end='')
            print("")
