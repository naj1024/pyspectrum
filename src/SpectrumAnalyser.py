#!/bin/python3
"""
Provide a basic spectrum analyser for digitised complex samples


## TODOs
    * TODO: Convert inputs to streaming interfaces.
    * TODO: Drop receivers?
    * TODO: Markers on spectrogram during snapshot, for pre/post limits
    * TODO: Plugin for triggering snapshot on fft bin power, with masks
    * TODO: Add a seconds marker to the bottom (left) of the spectrogram
    * TODO: Change stream of spectrograms, again, to always put out 1inN, constant time between spectrums
    * TODO: png of each snapshot file?
"""

import datetime
import os
import pathlib
import time
import multiprocessing
import queue
import signal
import logging
import sys
import json
from typing import Tuple
from typing import Dict
from typing import Any

import numpy as np

from dataSources import DataSourceFactory
from dataSources import DataSource
from dataSink import DataSink_file
from dataProcessing import ProcessSamples
from misc import Ewma
from misc import PluginManager
from misc import Variables
from misc import SnapVariables
from misc import commandLine
from webUI import WebServer

processing = True  # global to be set to False from ctrl-c

# We will use separate log files for each process, main/webserver/websocket
# Perceived wisdom is to use a logging server in multiprocessing environments, maybe in the future
logger = logging.getLogger('spectrum_logger')

MAX_TO_UI_QUEUE_DEPTH = 4  # low for low latency, a high value will give a burst of contiguous spectrums at the start
MAX_FROM_UI_QUEUE_DEPTH = 10  # stop things backing up when no UI connected


def signal_handler(sig, __):
    global processing
    processing = False
    print("Received signal", sig)


def main() -> None:
    """
    Main programme

    :return: None
    """
    # logging to our own logger, not the base one - we will not see log messages for imported modules
    global logger
    # don't use %Z for timezone as some say 'GMT' or 'GMT standard time'
    logging.basicConfig(format='%(asctime)s,%(levelname)s:%(name)s:%(module)s:%(message)s',
                        datefmt="%Y-%m-%d %H:%M:%S UTC",
                        filemode='w',
                        filename="spec.log")
    logging.Formatter.converter = time.gmtime  # GMT/UTC timestamps on logging
    logger.setLevel(logging.INFO)

    logger.info("SpectrumAnalyser starting")

    # different python versions may impact us
    if sys.version_info < (3, 7):
        logger.warning(f"Python version means sample timings will be course, python V{sys.version}")

    global processing
    signal.signal(signal.SIGINT, signal_handler)

    # our configuration
    configuration = Variables.Variables()
    commandLine.parse_command_line(configuration, logger)

    # snapshot config
    snap_configuration = SnapVariables.SnapVariables()
    if not os.path.isdir(snap_configuration.baseDirectory):
        os.mkdir(snap_configuration.baseDirectory)
    list_snapshot_directory(snap_configuration)

    # check we have a valid input sample type
    if configuration.sample_type not in DataSource.supported_data_types:
        logger.critical(f'Illegal sample type of {configuration.sample_type} selected')
        quit()

    # all the sources available to us
    configuration.input_sources = DataSourceFactory.DataSourceFactory().sources()
    configuration.input_sources_web_helps = DataSourceFactory.DataSourceFactory().web_help_strings()

    # configure us
    data_source, display, to_ui_queue, to_ui_control_queue, from_ui_queue, processor, plugin_manager, source_factory = initialise(
        configuration)
    snap_configuration.cf = configuration.centre_frequency_hz
    snap_configuration.sps = configuration.sample_rate
    data_sink = DataSink_file.FileOutput(snap_configuration)

    # allowed sample types for base source converter
    configuration.sample_types = data_source.get_sample_types()

    # The amount of time to get samples
    expected_samples_receive_time = configuration.fft_size / configuration.sample_rate
    logger.info(f"SPS: {configuration.sample_rate / 1e6:0.3}MHzs "
                f"RBW: {(configuration.sample_rate / (configuration.fft_size * 1e3)):0.1f}kHz")
    logger.info(f"Samples {configuration.fft_size}: {(1000000 * expected_samples_receive_time):.0f}usec")
    logger.info(f"Required FFT per second: {configuration.sample_rate / configuration.fft_size:.0f}")

    # expected bits/sec on network, 8bits byte, 4 bytes per complex
    bits_sec = configuration.sample_rate * 8 * data_source.get_bytes_per_sample()
    logger.info(f"Minimum bit rate of input: {(bits_sec / 1e6):.0f}Mbit/sec")

    # configure some default things before the main loop
    peak_powers_since_last_display = np.full(configuration.fft_size, -200)
    sample_get_time = Ewma.Ewma(0.01)
    process_time = Ewma.Ewma(0.01)
    debug_time = 0
    config_time = 0  # when we will send our config to the UI
    fps_update_time = 0

    # keep processing until told to stop or an error occurs
    peak_average = Ewma.Ewma(0.1)
    current_peak_count = 0
    max_peak_count = 0
    while processing:

        if not multiprocessing.active_children():
            processing = False  # we will exit mow as we lost our processes

        # if there is a control message then it may change whats happening
        data_source, data_sink = handle_from_ui_queue(configuration, snap_configuration,
                                                      to_ui_control_queue, from_ui_queue,
                                                      data_source, source_factory, data_sink)

        ###########################################
        # Get and process the complex samples we will work on
        ######################
        try:
            data_samples_perf_time_start = time.perf_counter()
            samples, time_rx_nsec = data_source.read_cplx_samples()
            data_samples_perf_time_end = time.perf_counter()

            _ = sample_get_time.average(data_samples_perf_time_end - data_samples_perf_time_start)
            if samples is None:
                time.sleep(0.001)  # rate limit on trying to get samples
            else:
                # record start time so we can average how long processing is taking
                complete_process_time_start = time.perf_counter()

                ##########################
                # Calculate the spectrum
                #################
                processor.process(samples)

                ###########################
                # analysis of the spectrum
                #################
                results = plugin_manager.call_plugin_method(method="analysis",
                                                            args={"powers": processor.get_powers(False),
                                                                  "noise_floors": processor.get_long_average(False),
                                                                  "reordered": False})

                #####################
                # reporting results
                #############
                if "peaks" in results and len(results["peaks"]) > 0:
                    freqs = ProcessSamples.convert_to_frequencies(results["peaks"],
                                                                  configuration.sample_rate,
                                                                  configuration.fft_size)
                    _ = plugin_manager.call_plugin_method(method="report",
                                                          args={"data_samples_time": time_rx_nsec,
                                                                "frequencies": freqs,
                                                                "centre_frequency_hz":
                                                                    configuration.centre_frequency_hz})

                ##########################
                # Handle snapshots
                # -- this may alter sample values
                # due to pre-trigger we need to always give the samples
                #################
                if data_sink.write(snap_configuration.triggered, samples, time_rx_nsec):
                    snap_configuration.triggered = False
                    snap_configuration.triggerState = "wait"
                    snap_configuration.snapState = "stop"
                    list_snapshot_directory(snap_configuration)  # update the list
                snap_configuration.currentSizeMbytes = data_sink.get_current_size_mbytes()
                snap_configuration.expectedSizeMbytes = data_sink.get_size_mbytes()

                # has underlying sps or cf changed for the snap
                if snap_configuration.cf != configuration.centre_frequency_hz or \
                        snap_configuration.sps != configuration.sample_rate:
                    snap_configuration.cf = configuration.centre_frequency_hz
                    snap_configuration.sps = configuration.sample_rate
                    snap_configuration.triggered = False
                    snap_configuration.triggerState = "wait"
                    snap_configuration.snapState = "stop"
                    data_sink = DataSink_file.FileOutput(snap_configuration)
                    snap_configuration.currentSizeMbytes = 0
                    snap_configuration.expectedSizeMbytes = data_sink.get_size_mbytes()

                ##########################
                # Update the UI
                #################
                peak_powers_since_last_display, current_peak_count, max_peak_count = \
                    update_ui(configuration,
                              to_ui_queue,
                              processor.get_powers(False),
                              peak_powers_since_last_display,
                              current_peak_count,
                              max_peak_count,
                              time_rx_nsec)

                # average of number of count of spectrums between UI updates
                peak_average.average(max_peak_count)

                complete_process_time_end = time.perf_counter()  # time for everything but data get
                process_time.average(complete_process_time_end - complete_process_time_start)

        except ValueError:
            # incorrect number of samples, probably because something closed
            if processing:
                data_source.close()
                err_msg = f"Problem with source {configuration.input_source}"
                configuration.input_source = "null"
                data_source = update_source(configuration, source_factory)
                configuration.error += err_msg
                logger.error(configuration.error)

        now = time.time()
        if now > fps_update_time:
            configuration.measured_fps = measure_fps(expected_samples_receive_time,
                                                     process_time,
                                                     sample_get_time,
                                                     peak_average.get_ewma())
            fps_update_time = now + 2

        # Debug print on how long things are taking
        if now > debug_time:
            debug_print(expected_samples_receive_time,
                        configuration.fft_size, process_time,
                        sample_get_time,
                        peak_average.get_ewma(),
                        configuration.fps,
                        configuration.measured_fps,
                        configuration.oneInN)
            debug_time = now + 6

        if now > config_time:
            # check on the source
            update_source_state(configuration, data_source)
            config_time = now + 1
            # is there space
            try:
                # Send the current configuration to the UI
                to_ui_control_queue.put(configuration.make_json(), block=False)
                configuration.error = ""  # reset any error we reported
                to_ui_control_queue.put(snap_configuration.make_json(), block=False)
            except queue.Full:
                pass

    ####################
    #
    # clean up
    #
    #############
    if data_source:
        logger.debug("SpectrumAnalyser data_source close")
        data_source.close()

    if display:
        logger.debug(f"Shutting down children, {multiprocessing.active_children()}")
        if multiprocessing.active_children():
            # belt and braces
            display.terminate()
            display.shutdown()
            display.join()

    if to_ui_queue:
        while not to_ui_queue.empty():
            _ = to_ui_queue.get()
        logger.debug("SpectrumAnalyser to_ui_queue empty")

    if to_ui_control_queue:
        while not to_ui_control_queue.empty():
            _ = to_ui_control_queue.get()
        logger.debug("SpectrumAnalyser to_ui_control_queue empty")

    logger.error("SpectrumAnalyser exit")


# Problem defining what we return, DataSource can be many different things
# def initialise(configuration: Variables) -> Tuple[...]:
def initialise(configuration: Variables):
    """
    Initialise everything we need

    :param configuration: How we will be configured
    :return:
    """
    try:
        # where we get our input samples from
        factory = DataSourceFactory.DataSourceFactory()
        # check that it is supported
        if configuration.input_source not in factory.sources():
            print("Available sources: ", factory.sources())
            raise ValueError(f"Error: Input source type of '{configuration.input_source}' is not supported")

        # Queues for UI, control and data are separate when going to ui
        to_ui_queue = multiprocessing.Queue(MAX_TO_UI_QUEUE_DEPTH)
        to_ui_control_queue = multiprocessing.Queue(MAX_TO_UI_QUEUE_DEPTH)
        # queue from ui only has control
        from_ui_queue = multiprocessing.Queue(MAX_FROM_UI_QUEUE_DEPTH)

        display = WebServer.WebServer(to_ui_queue, to_ui_control_queue, from_ui_queue,
                                      logger.level, configuration.web_port)
        display.start()
        logger.debug(f"Started WebServer, {display}")

        # plugins, pass in all the variables as we don't know what the plugin may require
        plugin_manager = PluginManager.PluginManager(plugin_init_arguments=vars(configuration))

        data_source = create_source(configuration, factory)
        try:
            open_source(configuration, data_source)
        except ValueError as msg:
            logger.error(f"Connection problem {msg}")
            configuration.error += str(msg)

        # The main processor for producing ffts etc
        processor = ProcessSamples.ProcessSamples(configuration)

        return data_source, display, to_ui_queue, to_ui_control_queue, from_ui_queue, processor, plugin_manager, factory

    except Exception as msg:
        # exceptions here are fatal
        raise msg


def list_snapshot_directory(snap_config: SnapVariables) -> None:
    directory = pathlib.PurePath(snap_config.baseDirectory)
    snap_config.directory_list = []
    for path in pathlib.Path(directory).iterdir():
        filename = os.path.basename(path)
        if not filename.startswith("."):
            # We will not match the time in the filename as it is recording the trigger time
            # getctime() may also return the last modification time not creation time (dependent on OS)
            timestamp = int(os.path.getctime(path))
            date_time = datetime.datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d_%H-%M-%S')
            snap_config.directory_list.append((filename,
                                               str(round(os.path.getsize(path) / (1024 * 1024), 3)),
                                               date_time))
    # sort so that most recent is first
    snap_config.directory_list.sort(reverse=True, key=lambda a: a[2])


def create_source(configuration: Variables, factory) -> DataSource:
    """
    Create the source of samples, cannot exception or fail. Does not open the source.

    :param configuration: All the config we need
    :param factory: Where we get the source from
    :return: The source, has still to be opened
    """
    data_source = factory.create(configuration.input_source,
                                 configuration.input_params,
                                 configuration.fft_size,
                                 configuration.sample_type,
                                 configuration.sample_rate,
                                 configuration.centre_frequency_hz,
                                 configuration.input_bw_hz)
    return data_source


def open_source(configuration: Variables, data_source: DataSource) -> None:
    """
    Open the source, just creating a source will not open it as the creation cannot fail but the open can

    :param configuration: Stores how the source is configured for our use
    :param data_source: The source we will open
    :return: None
    """
    # few other things to configure first before the open()
    data_source.set_gain_mode(configuration.gain_mode)
    data_source.set_gain(configuration.gain)

    if data_source.open():
        # may have updated various things
        configuration.sample_type = data_source.get_sample_type()
        configuration.sample_rate = data_source.get_sample_rate_sps()
        configuration.centre_frequency_hz = data_source.get_centre_frequency_hz()
        configuration.gain = data_source.get_gain()
        configuration.gain_modes = data_source.get_gain_modes()
        configuration.gain_mode = data_source.get_gain_mode()
        configuration.input_bw_hz = data_source.get_bandwidth_hz()

        # patch up fps things
        configuration.oneInN = int(configuration.sample_rate /
                                   (configuration.fps * configuration.fft_size))

        # state any errors or warning
        configuration.source_connected = data_source.connected()

    configuration.error += data_source.get_and_reset_error()


def update_source_state(configuration: Variables, data_source: DataSource) -> None:
    """
    Things that the source may change on it's own that we need to be aware of for the UI etc

    :param configuration: How we think we are configured
    :param data_source:  Which source to check
    :return: None
    """
    if data_source:
        configuration.gain = data_source.get_gain()


def update_source(configuration: Variables, source_factory) -> DataSource:
    """
    Changing the source

    :param configuration: For returning how source is configured
    :param source_factory: How we will generate a new source
    :return: The DataSource
    """
    data_source = create_source(configuration, source_factory)
    try:
        open_source(configuration, data_source)
        configuration.error += data_source.get_and_reset_error()
        logger.info(f"Opened source {configuration.input_source}")
    except ValueError as msg:
        logger.error(f"Problem with new configuration, {msg} "
                     f"{configuration.centre_frequency_hz} "
                     f"{configuration.sample_rate} "
                     f"{configuration.fft_size}")
        configuration.error += str(msg)
        configuration.input_source = "null"
        data_source = create_source(configuration, source_factory)
        open_source(configuration, data_source)

    configuration.source_connected = data_source.connected()
    return data_source


def handle_snap_message(data_sink: DataSink_file, snap_config: SnapVariables,
                        new_config: Dict, sdr_config: Variables) -> DataSink_file:
    """
    messages from UI
    We may change the snap object here, data_sink, due to changes in cf, sps or configuration

    :param data_sink: where snap data will go, may change
    :param snap_config: current snap state etc
    :param new_config: dictionary from a json string with new configuration for snap
    :param sdr_config: sdr config so we can get cf, sps etc
    :return: None
    """
    changed = False
    if new_config['baseFilename'] != snap_config.baseFilename:
        snap_config.baseFilename = new_config['baseFilename']
        changed = True

    if new_config['snapState'] != snap_config.snapState:
        # only 'manual' type can change state here
        # don't set changed
        if snap_config.triggerType == "manual":
            snap_config.snapState = new_config['snapState']
            if snap_config.snapState == "start":
                snap_config.triggered = True
                snap_config.triggerState = "triggered"
            else:
                snap_config.triggered = False
                snap_config.triggerState = "wait"
                snap_config.snapState = "stop"

    if new_config['preTriggerMilliSec'] != snap_config.preTriggerMilliSec:
        snap_config.preTriggerMilliSec = new_config['preTriggerMilliSec']
        changed = True

    if new_config['postTriggerMilliSec'] != snap_config.postTriggerMilliSec:
        snap_config.postTriggerMilliSec = new_config['postTriggerMilliSec']
        changed = True

    if new_config['triggerType'] != snap_config.triggerType:
        snap_config.triggerType = new_config['triggerType']  # don't set changed

    # has any non-snap setting changed
    if sdr_config.centre_frequency_hz != snap_config.cf or sdr_config.sample_rate != snap_config.sps:
        snap_config.cf = sdr_config.centre_frequency_hz
        snap_config.sps = sdr_config.sample_rate
        changed = True

    if new_config['deleteFileName'] != "":
        delete_file(new_config['deleteFileName'], snap_config, sdr_config)

    if changed:
        data_sink = DataSink_file.FileOutput(snap_config)
        # following may of been changed by the sink
        if data_sink.get_post_trigger_milli_seconds() != snap_config.postTriggerMilliSec or \
                data_sink.get_pre_trigger_milli_seconds() != snap_config.preTriggerMilliSec:
            snap_config.postTriggerMilliSec = data_sink.get_post_trigger_milli_seconds()
            snap_config.preTriggerMilliSec = data_sink.get_pre_trigger_milli_seconds()
            sdr_config.error += f"Snap modified to maximum file size of {snap_config.max_file_size / 1e6}MBytes"

    return data_sink


def delete_file(filename: str, snap_config: SnapVariables, sdr_config: Variables) -> None:
    file = pathlib.PurePath(snap_config.baseDirectory + "/" + filename)
    try:
        os.remove(file)
    except OSError as msg:
        err = f"Problem with delete of {filename}, {msg}"
        logger.error(err)
        sdr_config.error = err

    list_snapshot_directory(snap_config)


def handle_sdr_message(configuration: Variables, new_config: Dict, data_source, source_factory) -> DataSource:
    """
    Handle specific sdr related control messages
    :param configuration: current config
    :param new_config: dictionary from a json string with possible new config
    :param data_source: where we get data from currently
    :param source_factory:
    :return: DataSource
    """
    if (new_config['source'] != configuration.input_source) \
            or (new_config['sourceParams'] != configuration.input_params) \
            or (new_config['dataFormat'] != configuration.sample_type):
        configuration.input_source = new_config['source']
        configuration.input_params = new_config['sourceParams']
        configuration.sample_type = new_config['dataFormat']
        configuration.centre_frequency_hz = new_config['centreFrequencyHz']
        logger.info(f"changing source to '{configuration.input_source}' "
                    f"'{configuration.input_params}' '{configuration.sample_type}'")
        data_source.close()
        data_source = update_source(configuration, source_factory)
    else:
        if new_config['centreFrequencyHz'] != configuration.centre_frequency_hz:
            new_cf = new_config['centreFrequencyHz']
            data_source.set_centre_frequency_hz(new_cf)
            configuration.error += data_source.get_and_reset_error()
            configuration.centre_frequency_hz = data_source.get_centre_frequency_hz()

        if new_config['sdrBwHz'] != configuration.input_bw_hz:
            new_bw = new_config['sdrBwHz']
            data_source.set_bandwidth_hz(new_bw)
            configuration.error += data_source.get_and_reset_error()
            configuration.input_bw_hz = data_source.get_bandwidth_hz()

        if new_config['sps'] != configuration.sample_rate:
            new_sps = new_config['sps']
            data_source.set_sample_rate_sps(new_sps)
            configuration.error += data_source.get_and_reset_error()
            configuration.sample_rate = data_source.get_sample_rate_sps()
            configuration.oneInN = int(configuration.sample_rate /
                                       (configuration.fps * configuration.fft_size))

        if new_config['fftSize'] != configuration.fft_size:
            configuration.fft_size = new_config['fftSize']
            configuration.oneInN = int(configuration.sample_rate /
                                       (configuration.fps * configuration.fft_size))
            data_source.close()
            data_source = update_source(configuration, source_factory)

        if new_config['gain'] != configuration.gain:
            configuration.gain = new_config['gain']
            data_source.set_gain(configuration.gain)
            configuration.error += data_source.get_and_reset_error()
            configuration.gain = data_source.get_gain()

        if new_config['gainMode'] != configuration.gain_mode:
            configuration.gain_mode = new_config['gainMode']
            data_source.set_gain_mode(configuration.gain_mode)
            configuration.error += data_source.get_and_reset_error()
            configuration.gain_mode = data_source.get_gain_mode()

    return data_source


def handle_from_ui_queue(configuration: Variables,
                         snap_configuration: SnapVariables,
                         to_ui_control_queue: multiprocessing.Queue,
                         from_ui_queue: multiprocessing.Queue,
                         data_source,
                         source_factory,
                         snap_sink) -> Tuple[Any, Any]:
    """
    Check the control queue for messages and handle them

    :param configuration: the current configuration
    :param snap_configuration: the current snapshot config
    :param to_ui_control_queue: The queue used for talking to the UI process
    :param from_ui_queue: The queue to check on
    :param data_source:
    :param source_factory:
    :param snap_sink:
    :return: DataSource and snapSink, either of which may of changed
    """
    config = None
    try:
        config = from_ui_queue.get(block=False)
    except queue.Empty:
        pass

    if config:
        # config message is a json string
        # e.g. {"type":"sdrUpdate","name":"unknown","centreFrequencyHz":433799987,"sps":600000,
        #       "bw":600000,"fftSize":"8192","sdrStateUpdated":false}
        new_config = None
        try:
            new_config = json.loads(config)
        except ValueError as msg:
            logger.error(f"Problem with json control message {config}, {msg}")

        if new_config:
            if new_config['type'] == "null":
                pass
            elif new_config['type'] == "fps":
                configuration.fps = int(new_config['value'])
                if configuration.fps > 0:
                    configuration.oneInN = int(configuration.sample_rate /
                                               (configuration.fps * configuration.fft_size))
            elif new_config['type'] == "ack":
                # time of last UI processed data
                configuration.ack = int(new_config['value'])
            elif new_config['type'] == "stop":
                configuration.stop = int(new_config['value'])
            elif new_config['type'] == "snapUpdate":
                snap_sink = handle_snap_message(snap_sink,
                                                snap_configuration,
                                                new_config,
                                                configuration)
            elif new_config['type'] == "sdrUpdate":
                # we may be directed to change the source
                data_source = handle_sdr_message(configuration, new_config, data_source, source_factory)
            else:
                logger.error(f"Unknown control json from client {new_config}")
                print(f"Unknown control json from client {new_config}")

            # reply with the current configuration whenever we receive something on the control queue
            try:
                to_ui_control_queue.put(configuration.make_json(), block=False)
                configuration.error = ""  # reset any error we are reporting
            except queue.Full:
                pass

    return data_source, snap_sink


def update_ui(configuration: Variables,
              to_ui_queue: multiprocessing.Queue,
              powers: np.ndarray,
              peak_powers_since_last_display: np.ndarray,
              current_peak_count: int,
              max_peak_count: int,
              time_spectrum: float) -> Tuple[np.ndarray, int, int]:
    """
    Send data to the queue used for talking to the ui processes

    :param configuration: Our programme state variables
    :param to_ui_queue: The queue used for talking to the UI process
    :param powers: The powers of the spectrum bins
    :param peak_powers_since_last_display: The powers since we last updated the UI
    :param current_peak_count: count of spectrums we have peak held on
    :param max_peak_count: maximum since last time it was reset
    :param time_spectrum: Time of this spectrum in nano seconds
    :return: array of updated peak powers
    """

    peak_detect = False
    # drop things on the floor if we are told to stop
    if configuration.stop:
        configuration.measured_fps = 0  # not doing anything yet
    else:
        configuration.update_count += 1

        # should we try and add to the ui queue
        if configuration.update_count >= configuration.oneInN:
            configuration.update_count = 0
            # timings need to be altered
            if current_peak_count == 1:
                configuration.time_first_spectrum = time_spectrum

            # order the spectral magnitudes, zero in the middle
            display_peaks = np.fft.fftshift(peak_powers_since_last_display)

            # data into the UI queue
            try:
                to_ui_queue.put((configuration.sample_rate, configuration.centre_frequency_hz,
                                 display_peaks, configuration.time_first_spectrum, time_spectrum), block=False)

                # peak since last time is the current powers
                max_peak_count = current_peak_count
                current_peak_count = 0
                peak_powers_since_last_display = powers
                configuration.time_first_spectrum = time_spectrum
            except queue.Full:
                peak_detect = True  # UI can't keep up
        else:
            peak_detect = True

        current_peak_count += 1  # count even when we throw them away

        # Is the UI keeping up with how fast we are sending things
        # rather a lot of data may get buffered by the OS or network stack
        seconds = time_spectrum / 1e9
        ack = configuration.ack
        if ack == 0:
            ack = seconds
        diff = int(seconds - ack)
        if diff > 3 and configuration.fps > 20:
            logger.info(f"UI not keeping up last ack {ack}, current data {int(seconds)}, diff {int(seconds - ack)}")
            # As new fps is done here the webSocketServer process will be reading too fast and cause stuttering
            # take it as a feature that gives feedback, unless the UI updates the fps and feeds it back to us
            configuration.fps = 20  # something safe and sensible
            configuration.ack = seconds
            configuration.error += f"FPS too fast, UI behind by {diff}seconds. Defaulting to 20fps"
            configuration.oneInN = int(configuration.sample_rate /
                                       (configuration.fps * configuration.fft_size))
            peak_detect = True  # UI can't keep up

    if peak_detect:
        if powers.shape == peak_powers_since_last_display.shape:
            # Record the maximum for each bin, so that ui can show things between display updates
            peak_powers_since_last_display = np.maximum.reduce([powers, peak_powers_since_last_display])
        else:
            peak_powers_since_last_display = powers

    return peak_powers_since_last_display, current_peak_count, max_peak_count


def measure_fps(expect_samples_receive_time: float,
                process_time: Ewma,
                sample_get_time: Ewma,
                peak_count: float) -> int:
    """
    Approx measured fps

    :param expect_samples_receive_time: How long the samples would of taken to digitise
    :param process_time: How long we have spent processing the samples
    :param sample_get_time: How long it took as to receive the digitised samples
    :param peak_count: Count of how many spectrums we are peak detecting on for the UI
    :return: approx fps
    """
    fps = -1
    total_time = sample_get_time.get_ewma() + process_time.get_ewma()
    if peak_count > 0:
        if total_time > 0:
            fps = 1 / (total_time * peak_count)
    else:
        # running real time
        fps = 1 / expect_samples_receive_time
    return int(fps)


def debug_print(expect_samples_receive_time: float,
                fft_size: int,
                process_time: Ewma,
                sample_get_time: Ewma,
                peak_count: float,
                fps: int,
                mfps: int,
                one_in_n: int):
    """
    Various useful profiling prints

    :param expect_samples_receive_time: How long the samples would of taken to digitise
    :param fft_size: The number of samples per cycle
    :param process_time: How long we have spent processing the samples
    :param sample_get_time: How long it took as to receive the digitised samples
    :param peak_count: Count of how many spectrums we are peak detecting on for the UI
    :param fps: requested fps
    :param mfps: measured fps
    :param one_in_n: One in N sent to UI

    :return: None
    """
    total_time = sample_get_time.get_ewma() + process_time.get_ewma()
    logger.debug(f'FFT:{fft_size} '
                 f'{1e6 * expect_samples_receive_time:.0f}usec, '
                 f'read:{1e6 * sample_get_time.get_ewma():.0f}usec, '
                 f'process:{1e6 * process_time.get_ewma():.0f}usec, '
                 f'total:{1e6 * total_time:.0f}usec, '
                 f'pc:{peak_count:0.1f}, '
                 f'fps:{fps}, '
                 f'mfps:{mfps}, '
                 f'1inN:{one_in_n} ')


if __name__ == '__main__':
    main()
