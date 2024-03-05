import json
import logging
import textwrap
import time
from typing import List

from misc.PluginManager import Plugin

logger = logging.getLogger('spectrum_logger')

# try and import mqtt library
mqtt_available = True
mqtt = None
try:
    # noinspection PyUnresolvedReferences
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt_available = False

default_broker_address = ""
default_base_topic = "spectrum"
help_string = textwrap.dedent(f'''
              Report type plugin. 
                Sends results to an MQTT broker.
                Takes options:
                    --plugin report:mqtt:broker:ip-address-name
                    --plugin report:mqtt:topic:spectrum
                    --plugin report:mqtt:enabled:on
                default broker address: "{default_broker_address}"
                default base topic: "{default_base_topic}"
                default enabled:off''')


class Mqtt(Plugin):
    def __init__(self, **kwargs):
        # Note we need to have a class method for each entry in the self_methods list
        # and the name has to match
        self._methods = ['report']
        self._enabled = False
        self._base_topic = default_base_topic
        self._mqtt_broker_address = ""
        self._mqtt_client = None
        self._help_string = help_string
        self._parse_options(kwargs)

        if self._enabled:
            # if the mqtt broker address is not set then we will not create a client
            if self._mqtt_broker_address:
                self._mqtt_client = mqtt.Client("mqttStats")  # create new instance
                logger.info(f"Connecting to MQTT broker at: {self._mqtt_broker_address}")
                try:
                    self._mqtt_client.connect(self._mqtt_broker_address)  # connect to broker
                    self._mqtt_client.loop_start()  # start the loop
                    logger.info("Connected to MQTT broker")
                except OSError as msg:
                    logger.error("MQTT connection failed,", msg)
                    self._mqtt_client = None

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
                        # --plugin report:mqtt:broker:ip-address-name
                        if parts[0] == "report" and parts[1] == "mqtt" and parts[2] == "broker":
                            self._mqtt_broker_address = parts[3]

                        # --plugin report:mqtt:topic:spectrum
                        if parts[0] == "report" and parts[1] == "mqtt" and parts[2] == "topic":
                            self._base_topic = parts[3]

                        # --plugin report:mqtt:enabled:on
                        if parts[0] == "report" and parts[1] == "mqtt" and parts[2] == "enabled":
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
        Send things to the MQTT broker

        :param data_samples_time: Time of samples that caused an event
        :param frequencies: List of frequencies offsets that were found
        :param centre_frequency_hz: The centre frequency for the list of frequency offsets
        :return: None
        """
        # we will only process if we have a connection to a mqtt broker
        if self._enabled and self._mqtt_client:
            secs = int(data_samples_time / 1e9)
            micro_secs = int(((data_samples_time / 1e9) - secs) * 1000)

            events_topic = self._base_topic + "/event"
            happened_at = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(secs))
            self._mqtt_client.publish(events_topic, json.dumps((happened_at, micro_secs, len(frequencies))))

            frequency_topic = self._base_topic + "/freqs"
            freqs = [int(x + centre_frequency_hz) for x in frequencies]
            # JSON of gmtime,perf_count,integer_frequencies
            self._mqtt_client.publish(frequency_topic, json.dumps((happened_at, micro_secs, freqs)))
