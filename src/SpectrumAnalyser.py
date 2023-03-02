#!/bin/python3
"""
Provide a basic spectrum analyser for digitised complex samples

## TODOs, in no particular order
    * TODO: Add a seconds marker to the bottom (left) of the spectrogram
    * TODO: Plugin for triggering snapshot on fft bin power, with masks
    * TODO: On web interface update just the rows that changed on the configuration table
    * TODO: On web interface config and snap tables change to just update the current not the new cells
    * TODO: On web interface is there a way to update the help when a different source is selected
    * TODO: On web interface why don't the interval functions for updating things work
    * TODO: Generic way to handle data sources with unique parameters
    * TODO: UI responsiveness is tied to data arriving, should be independent of arriving spectrum data
    * TODO: Favourites tab for source, freq, rate etc
    * TODO: Support controlling the FUNcube, frequency done on linux but not windows
    * TODO: sample rate, centre frequency, bandwidths need to handle ranges and discrete lists
"""

import logging
import multiprocessing
import os
import pathlib
import queue
import signal
import sys
import time
from typing import Tuple
from typing import Type

import numpy as np

from dataProcessing import ProcessSamples
from dataSink import DataSink_file
from dataSources import DataSource
from dataSources import DataSourceFactory
from misc import Ewma
from misc import PicGenerator
from misc import PluginManager
from misc import SdrVariables
from misc import SnapVariables
from misc import commandLine
from misc import global_vars
from misc import sdrStuff
from misc import snapStuff
from webUI import FlaskInterface
from webUI import WebSocketServer

processing = True  # global to be set to False from ctrl-c

# We will use separate log files for each process, main/webserver/websocket
# Perceived wisdom is to use a logging server in multiprocessing environments, maybe in the future
logger = logging.getLogger("spectrum_logger")  # a name we use to find this logger

MAX_TO_UI_QUEUE_DEPTH = 10  # low for low latency


def signal_handler(sig, __):
    global processing
    processing = False
    print("Received signal", sig)


def main() -> None:
    """
    Main programme

    :return: None
    """
    signal.signal(signal.SIGINT, signal_handler)

    # default config and setup
    configuration, snap_configuration, thumbs_dir = setup()
    logger.info("SpectrumAnalyser started")

    # different python versions may impact us
    if sys.version_info < (3, 7):
        logger.warning(f"Python version nas no support for nanoseconds, current interpreter is V{sys.version}")

    # configuration shared across all processes
    manager = multiprocessing.Manager()
    multip_config = manager.dict()

    # all our things
    data_source, display, websocket, to_ui_queue, processor, plugin_manager, source_factory, pic_generator, \
        multip_config = initialise(configuration, snap_configuration, thumbs_dir, multip_config)

    # the snapshot config
    snap_configuration.cf = configuration.centre_frequency_hz
    snap_configuration.sps = configuration.sample_rate
    data_sink = DataSink_file.FileOutput(snap_configuration, SnapVariables.SNAPSHOT_DIRECTORY)

    # Some info on the amount of time to get samples
    expected_samples_receive_time = configuration.fft_size / configuration.sample_rate
    logger.info(f"SPS: {configuration.sample_rate / 1e6:0.3}MHzs "
                f"RBW: {(configuration.sample_rate / (configuration.fft_size * 1e3)):0.1f}kHz")
    logger.info(f"Samples {configuration.fft_size}: {(1000000 * expected_samples_receive_time):.0f}usec")
    logger.info(f"Required FFT per second: {configuration.sample_rate / configuration.fft_size:.0f}")

    # expected bits/sec on network, 8bits byte, 4 bytes per complex
    bits_sec = 8 * configuration.sample_rate * data_source.get_bytes_per_complex_sample() * configuration.fft_size
    logger.info(f"Minimum bit rate of input: {(bits_sec / 1e6):.0f}Mbit/sec")

    # Default things before the main loop
    peak_powers_since_last_display = np.full(configuration.fft_size, -200)
    # timing things, averages
    capture_time = Ewma.Ewma(0.01)
    process_time = Ewma.Ewma(0.01)
    analysis_time = Ewma.Ewma(0.01)
    reporting_time = Ewma.Ewma(0.01)
    snap_time = Ewma.Ewma(0.01)
    ui_time = Ewma.Ewma(0.01)
    debug_time = 0
    config_time = 0  # when we will send our config to the UI
    fps_update_time = 0

    # keep processing until told to stop or an error occurs
    peak_average = Ewma.Ewma(0.1)
    current_peak_count = 0
    max_peak_count = 0
    config_changed = False
    global processing
    while processing:

        if not multiprocessing.active_children():
            processing = False  # we will exit mow as we lost our processes

        # sync the config from multiprocessing
        data_source, data_sink, configuration, snap_configuration, config_changed = \
            sync_config(configuration, snap_configuration,
                        data_source, source_factory, data_sink,
                        thumbs_dir, processor, multip_config, config_changed)

        ###########################################
        # Get and process the complex samples we will work on
        ######################
        try:
            if not configuration.stop:
                time_start = time.perf_counter()
                samples, time_rx_nsec = data_source.read_cplx_samples(configuration.fft_size)
                time_end = time.perf_counter()
                configuration.input_overflows = data_source.get_overflows()
            else:
                samples = None

            # stop doing cpu heavy things if we are told to stop
            #if configuration.stop:
            #    samples = None

            if samples is None:
                time.sleep(0.001)  # rate limit on trying to get samples
            else:
                _ = capture_time.average(time_end - time_start)
                # read ratio will be > 1.0 if we take longer to get samples than we expect
                # it should be less than we expect as the driver will be getting samples while we do other things
                configuration.read_ratio = (configuration.sample_rate * capture_time.get_ewma()) / configuration.fft_size

                # record start time so we can average how long processing is taking
                time_start = time.perf_counter()

                ##########################
                # Calculate the spectrum
                #################
                processor.process(samples)
                time_end = time.perf_counter()
                process_time.average(time_end - time_start)

                ###########################
                # analysis of the spectrum
                #################
                time_start = time.perf_counter()
                results = plugin_manager.call_plugin_method(method="analysis",
                                                            args={"powers": processor.get_powers(False),
                                                                  "noise_floors": processor.get_long_average(False),
                                                                  "reordered": False})

                time_end = time.perf_counter()
                analysis_time.average(time_end - time_start)

                #####################
                # reporting results
                #############
                time_start = time.perf_counter()
                if "peaks" in results and len(results["peaks"]) > 0:
                    freqs = ProcessSamples.convert_to_frequencies(results["peaks"],
                                                                  configuration.sample_rate,
                                                                  configuration.fft_size)
                    _ = plugin_manager.call_plugin_method(method="report",
                                                          args={"data_samples_time": time_rx_nsec,
                                                                "frequencies": freqs,
                                                                "centre_frequency_hz":
                                                                    configuration.centre_frequency_hz})

                time_end = time.perf_counter()
                reporting_time.average(time_end - time_start)

                ##########################
                # Handle snapshots
                # -- this may alter sample values
                # due to pre-trigger we need to always give the samples
                #################
                time_start = time.perf_counter()
                if data_sink.write(snap_configuration.triggered, samples, time_rx_nsec):
                    snap_configuration.triggered = False
                    snap_configuration.triggerState = "wait"
                    snap_configuration.directory_list = snapStuff.list_snap_files(SnapVariables.SNAPSHOT_DIRECTORY)
                    config_changed = True

                snap_configuration.currentSizeMbytes = data_sink.get_current_size_mbytes()
                snap_configuration.expectedSizeMbytes = data_sink.get_size_mbytes()

                time_end = time.perf_counter()
                snap_time.average(time_end - time_start)

                time_start = time.perf_counter()

                # has underlying sps or cf changed for the snap
                # if snap_configuration.cf != configuration.real_centre_frequency_hz or \
                #         snap_configuration.sps != configuration.sample_rate:
                #     snap_configuration.cf = configuration.real_centre_frequency_hz
                #     snap_configuration.sps = configuration.sample_rate
                #     snap_configuration.triggered = False
                #     snap_configuration.triggerState = "wait"
                #     data_sink = DataSink_file.FileOutput(snap_configuration, SnapVariables.SNAPSHOT_DIRECTORY)
                #     snap_configuration.currentSizeMbytes = 0
                #     snap_configuration.expectedSizeMbytes = data_sink.get_size_mbytes()
                #     config_changed = True

                if config_changed:
                    fill_config(multip_config, configuration, snap_configuration)
                    config_changed = False

                ##########################
                # Update the UI
                #################
                peak_powers_since_last_display, current_peak_count, max_peak_count = \
                    send_to_ui(configuration,
                               to_ui_queue,
                               processor.get_powers(False),
                               peak_powers_since_last_display,
                               current_peak_count,
                               max_peak_count,
                               time_rx_nsec)
                time_end = time.perf_counter()
                ui_time.average(time_end - time_start)

                # average of number of count of spectrums between UI updates
                peak_average.average(max_peak_count)

        except ValueError:
            # incorrect number of samples, probably because something closed
            if processing:
                data_source.close()
                err_msg = f"Problem with source: {configuration.input_source}"
                configuration.input_source = "null"
                data_source = sdrStuff.update_source(configuration, source_factory)
                SdrVariables.add_to_error(configuration, err_msg)
                logger.error(configuration.error)

        now = time.time()
        if now > fps_update_time:
            if (now - configuration.time_measure_fps) > 0:
                configuration.measured_fps = round(configuration.sent_count / (now - configuration.time_measure_fps), 1)
            fps_update_time = now + 1
            configuration.time_measure_fps = now
            configuration.sent_count = 0
            fill_config_fast(multip_config, configuration, snap_configuration)

        # Debug print on how long things are taking
        if now > debug_time:
            debug_print(configuration.sample_rate,
                        configuration.fft_size,
                        capture_time,
                        process_time,
                        analysis_time,
                        reporting_time,
                        snap_time,
                        ui_time,
                        peak_average.get_ewma(),
                        configuration.fps,
                        configuration.measured_fps)
            debug_time = now + 6

        if now > config_time:
            # check on the source, maybe the gain changed etc
            sdrStuff.update_source_state(configuration, data_source)
            config_time = now + 1
            total_time = process_time.get_ewma() + analysis_time.get_ewma() + reporting_time.get_ewma() + \
                            snap_time.get_ewma() + ui_time.get_ewma()
            data_time = (configuration.fft_size / configuration.sample_rate)
            configuration.headroom = 100.0 * (data_time - total_time) / data_time

    ####################
    #
    # clean up
    #
    #############
    if data_source:
        logger.debug("SpectrumAnalyser data_source close")
        data_source.close()

    if multiprocessing.active_children():
        logger.debug(f"Shutting down child processes, {multiprocessing.active_children()}")
        # belt and braces
        display.terminate()
        display.shutdown()
        display.join()
        websocket.terminate()
        websocket.shutdown()
        websocket.join()
        pic_generator.terminate()
        pic_generator.shutdown()
        pic_generator.join()

    if to_ui_queue:
        while not to_ui_queue.empty():
            _ = to_ui_queue.get()
        logger.debug("SpectrumAnalyser to_ui_queue empty")

    logger.error("SpectrumAnalyser exit")


def setup() -> Tuple[SdrVariables.SdrVariables, SnapVariables.SnapVariables, pathlib.PurePath]:
    """
    Basic things everything else use

    :return:
    """
    setup_logging("SpectrumAnalyser.log")

    # sdr configuration
    configuration = SdrVariables.SdrVariables()
    commandLine.parse_command_line(configuration, logger)

    # check we have a valid input sample type
    if configuration.sample_type not in DataSource.supported_data_types:
        raise ValueError(f'Illegal sample type of {configuration.sample_type} selected')

    # get all the sources available to us
    configuration.input_sources = DataSourceFactory.DataSourceFactory().sources()
    configuration.input_sources_with_helps = DataSourceFactory.DataSourceFactory().web_help_strings()

    # windowing
    configuration.window_types = ProcessSamples.get_windows()
    configuration.window = configuration.window_types[0]

    snap_configuration = setup_snap_config()
    thumbs_dir = setup_thumbs_dir()

    return configuration, snap_configuration, thumbs_dir


def setup_logging(log_filename: str) -> None:
    # logging to our own logger, not the base one - we will not see log messages for imported modules
    global logger
    try:
        os.mkdir(pathlib.PurePath(os.path.dirname(__file__), global_vars.log_dir))
    except FileExistsError:
        pass
    except Exception as msg:
        raise ValueError(f"Failed to create logging directory, {msg}")

    log_file = pathlib.PurePath(os.path.dirname(__file__), global_vars.log_dir, log_filename)
    try:
        # don't use %Z for timezone as some say 'GMT' or 'GMT standard time'
        logging.basicConfig(format='%(asctime)s,%(levelname)s:%(name)s:%(module)s:%(message)s',
                            datefmt="%Y-%m-%d %H:%M:%S UTC",
                            filemode='w',
                            filename=log_file)
    except Exception as msg:
        raise ValueError(f"Failed to create logger for main, {msg}")

    logging.Formatter.converter = time.gmtime  # GMT/UTC timestamps on logging
    logger.setLevel(logging.WARN)


def setup_snap_config() -> SnapVariables.SnapVariables:
    # make sure we have the snapshot directory
    snap_configuration = SnapVariables.SnapVariables()
    if not os.path.isdir(SnapVariables.SNAPSHOT_DIRECTORY):
        try:
            os.makedirs(SnapVariables.SNAPSHOT_DIRECTORY)
        except FileExistsError:
            pass
        except Exception as msg:
            raise ValueError(f"Failed to create snapshot directory, {msg}")
    snap_configuration.directory_list = snapStuff.list_snap_files(SnapVariables.SNAPSHOT_DIRECTORY)
    return snap_configuration


def setup_thumbs_dir() -> pathlib.PurePath:
    # web thumbnail directory
    where = f"{os.path.dirname(__file__)}"
    thumbs_dir = pathlib.PurePath(f"{where}/webUI/webroot/thumbnails")
    if not os.path.isdir(thumbs_dir):
        try:
            os.makedirs(thumbs_dir)
        except FileExistsError:
            pass
        except Exception as msg:
            print()
            raise ValueError(f"Failed to create web thumbnails directory, {msg}")
    return thumbs_dir


def initialise(configuration: SdrVariables, snap_config: SnapVariables, thumbs_dir: pathlib.PurePath, config: dict) \
        -> Tuple[Type[DataSource.DataSource],
                 FlaskInterface.FlaskInterface,
                 WebSocketServer.WebSocketServer,
                 multiprocessing.Queue,
                 ProcessSamples.ProcessSamples,
                 PluginManager.PluginManager,
                 DataSourceFactory.DataSourceFactory,
                 PicGenerator.PicGenerator,
                 dict]:
    """
     Initialise everything we need

    :param configuration: main config options
    :param snap_config: snapshot config options
    :param thumbs_dir: Where the picture generator will store thumbnails
    :param config: dictionary shared for multi-processing use
    :return: Lots
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

        fill_config(config, configuration, snap_config)

        display = FlaskInterface.FlaskInterface(to_ui_queue, logger.level, configuration.web_port, config)

        display.start()
        logger.debug(f"Started WebServer, {display}")

        web_socket = WebSocketServer.WebSocketServer(to_ui_queue, logger.level, configuration.web_port + 1)
        web_socket.start()
        logger.debug(f"Started WebSocket, {web_socket}")

        # plugins, pass in all the variables as we don't know what the plugin may require
        plugin_manager = PluginManager.PluginManager(plugin_init_arguments=vars(configuration))

        data_source = sdrStuff.create_source(configuration, factory)
        try:
            sdrStuff.open_source(configuration, data_source)

            # allowed sample source
            configuration.sample_types = data_source.get_sample_types()
        except ValueError as msg:
            logger.error(f"Connection problem {msg}")
            SdrVariables.add_to_error(configuration, str(msg))

        # The main processor for producing ffts etc
        processor = ProcessSamples.ProcessSamples(configuration)

        # thumbnail and pic generator process
        pic_generator = PicGenerator.PicGenerator(SnapVariables.SNAPSHOT_DIRECTORY, thumbs_dir, logger.level)
        pic_generator.start()
        logger.debug(f"Started PicGenerator")

        configuration.time_measure_fps = time.time()

        return data_source, display, web_socket, to_ui_queue, processor, plugin_manager, factory, pic_generator, config

    except Exception as msg:
        # exceptions here are fatal
        raise msg


def fill_config_fast(config: dict, configuration: SdrVariables, snap_config: SnapVariables):
    # things we want to update faster
    config['digitiserGain'] = configuration.gain

    # control stuff
    config['fps'] = ({'set': configuration.fps,
                      'measured': configuration.measured_fps})
    config['stop'] = configuration.stop
    config['delay'] = configuration.ui_delay
    config['readRatio'] = configuration.read_ratio
    config['headroom'] = configuration.headroom
    config['overflows'] = configuration.input_overflows
    config['oneInN'] = configuration.one_in_n

    # snapshot stuff
    config['snapTriggerState'] = snap_config.triggerState


def fill_config(config: dict, configuration: SdrVariables, snap_config: SnapVariables):
    # Half way house converting over from class containing configuration
    # to a dictionary,so we can use the multiproccessing dictionary between processes

    # source stuff
    # should really be paired up as source, help
    config['sources'] = configuration.input_sources_with_helps
    config['source'] = ({'source': configuration.input_source,
                         'params': configuration.input_params,
                         'connected': configuration.source_connected})

    # tuning stuff
    config['frequency'] = ({'value': configuration.centre_frequency_hz,
                            'conversion': configuration.conversion_frequency_hz})

    # digitiser stuff
    config['digitiserFrequency'] = configuration.sdr_centre_frequency_hz
    config['digitiserFormats'] = configuration.sample_types
    config['digitiserFormat'] = configuration.sample_type
    config['digitiserSampleRate'] = configuration.sample_rate
    config['digitiserBandwidth'] = configuration.input_bw_hz
    config['digitiserPartsPerMillion'] = configuration.ppm_error
    config['digitiserGainTypes'] = configuration.gain_modes
    config['digitiserGainType'] = configuration.gain_mode
    config['digitiserGain'] = configuration.gain

    # spectrum stuff
    config['fftSize'] = configuration.fft_size
    config['fftSizes'] = [256, 512, 1024, 2048, 4096, 8192, 16384, 32768]
    config['fftWindows'] = configuration.window_types
    config['fftWindow'] = configuration.window

    # control stuff
    config['fps'] = ({'set': configuration.fps,
                      'measured': configuration.measured_fps})
    config['presetFps'] = [1, 5, 10, 20, 40, 80, 160, 320, 640, 10000, 100000]
    config['stop'] = configuration.stop
    config['delay'] = configuration.ui_delay
    config['readRatio'] = configuration.read_ratio
    config['headroom'] = configuration.headroom
    config['overflows'] = configuration.input_overflows
    config['ackTime'] = configuration.ackTime
    config['oneInN'] = configuration.one_in_n

    # snapshot stuff
    config['snapTrigger'] = snap_config.triggered
    config['snapTriggerState'] = snap_config.triggerState
    config['snapTriggerSources'] = ['manual', 'off']
    config['snapTriggerSource'] = snap_config.triggerType
    config['snapName'] = snap_config.baseFilename
    config['snapFormats'] = snap_config.file_formats
    config['snapFormat'] = snap_config.file_format
    config['snapPreTrigger'] = snap_config.preTriggerMilliSec
    config['snapPostTrigger'] = snap_config.postTriggerMilliSec
    config['snaps'] = snap_config.directory_list
    config['snapSize'] = ({'current': snap_config.currentSizeMbytes,
                           'limit': snap_config.expectedSizeMbytes})
    config['snapDelete'] = ""


def sync_config(configuration: SdrVariables,
                snap_configuration: SnapVariables,
                data_source,
                source_factory,
                snap_sink,
                thumb_dir: pathlib.PurePath,
                processor: ProcessSamples,
                conf: dict,
                config_changed: bool):
    """

    :param configuration: config
    :param snap_configuration: config
    :param data_source: the current data source
    :param source_factory: for generating a new source
    :param snap_sink: the sink used for snapshots
    :param thumb_dir: Thumbnail directory
    :param processor: the current processor (fft's)
    :param conf: dictionary for sharing to mulit-processing
    :param config_changed: something has changed
    :return:
    """
    # -> Tuple[Type[DataSource.DataSource], DataSink_file.FileOutput,
    #                             SdrVariables, SnapVariables]:
    # conf  multiprocessing dictionary

    src = conf['source']
    if src['source'] != configuration.input_source or (src['params'] != configuration.input_params):
        data_source = sdrStuff.change_source(data_source, source_factory, configuration, src['source'], src['params'])
        if src['source'] == 'file':
            # need to configure things from the file
            if data_source.has_meta_data():
                conf['digitiserSampleRate'] = configuration.sample_rate
                conf['frequency'] = ({'value': configuration.centre_frequency_hz, 'conversion': 0})
                conf['digitiserFrequency'] = configuration.centre_frequency_hz
                conf['digitiserFormat'] = configuration.sample_type
        config_changed = True

    # if we have to override the fps as the UI is not keeping up then don't update the fps value
    if not configuration.fps_override:
        if conf['fps']['set'] != configuration.fps:
            configuration.fps = conf['fps']['set']
    else:
        conf['fps']['set'] = configuration.fps
        if configuration.measured_fps <= configuration.fps:
            # but if we are now keeping up then go back to normal
            configuration.fps_override = False

    if conf['ackTime'] != configuration.ackTime:
        configuration.ackTime = conf['ackTime']

    freq = conf['frequency']
    if freq['value'] != configuration.centre_frequency_hz \
            or freq['conversion'] != configuration.conversion_frequency_hz:
        new_sdr_cf = freq['value']
        new_dc = freq['conversion']
        if 0 < new_dc < new_sdr_cf:
            new_sdr_cf = new_sdr_cf - new_dc
        data_source.set_centre_frequency_hz(new_sdr_cf)
        SdrVariables.add_to_error(configuration, data_source.get_and_reset_error())

        # update our sdr frequency from what the sdr did
        configuration.sdr_centre_frequency_hz = data_source.get_centre_frequency_hz()
        configuration.centre_frequency_hz = freq['value']
        configuration.conversion_frequency_hz = new_dc
        config_changed = True

    if conf['digitiserBandwidth'] != configuration.input_bw_hz:
        data_source.set_bandwidth_hz(conf['digitiserBandwidth'])
        SdrVariables.add_to_error(configuration, data_source.get_and_reset_error())
        configuration.input_bw_hz = data_source.get_bandwidth_hz()
        config_changed = True

    if conf['digitiserPartsPerMillion'] != configuration.ppm_error:
        data_source.set_ppm(float(conf['digitiserPartsPerMillion']))
        SdrVariables.add_to_error(configuration, data_source.get_and_reset_error())
        configuration.ppm_error = data_source.get_ppm()
        config_changed = True

    if conf['digitiserSampleRate'] != configuration.sample_rate:
        data_source.set_sample_rate_sps(conf['digitiserSampleRate'])
        SdrVariables.add_to_error(configuration, data_source.get_and_reset_error())
        configuration.sample_rate = data_source.get_sample_rate_sps()
        config_changed = True

    if conf['stop'] != configuration.stop:
        configuration.stop = conf['stop']
        config_changed = True

    if conf['fftWindow'] != configuration.window:
        processor.set_window(conf['fftWindow'])
        configuration.window = processor.get_window()
        config_changed = True

    if conf['fftSize'] != configuration.fft_size:
        configuration.fft_size = conf['fftSize']
        config_changed = True

    if conf['digitiserGain'] != configuration.gain:
        configuration.gain = conf['digitiserGain']
        data_source.set_gain(configuration.gain)
        SdrVariables.add_to_error(configuration, data_source.get_and_reset_error())
        configuration.gain = data_source.get_gain()
        config_changed = True

    if conf['digitiserGainType'] != configuration.gain_mode:
        configuration.gain_mode = conf['digitiserGainType']
        data_source.set_gain_mode(configuration.gain_mode)
        SdrVariables.add_to_error(configuration, data_source.get_and_reset_error())
        configuration.gain_mode = data_source.get_gain_mode()
        config_changed = True

    if conf['digitiserFormat'] != configuration.sample_type:
        configuration.sample_type = conf['digitiserFormat']
        config_changed = True

    if conf['snapDelete'] != "":
        snapStuff.delete_file(conf['snapDelete'], thumb_dir)
        conf['snapDelete'] = ""
        snap_configuration.directory_list = snapStuff.list_snap_files(SnapVariables.SNAPSHOT_DIRECTORY)
        config_changed = True

    snap_changed = False
    if conf['snapTrigger'] and snap_configuration.triggerState != "triggered":
        if snap_configuration.triggerType == "manual":
            snap_configuration.triggered = True
            snap_configuration.triggerState = "triggered"
            config_changed = True

    if conf['snapTriggerSource'] != snap_configuration.triggerType:
        snap_configuration.triggerType = conf['snapTriggerSource']
        config_changed = True

    if conf['snapName'] != snap_configuration.baseFilename:
        snap_configuration.baseFilename = conf['snapName']
        config_changed = True
        snap_changed = True

    if conf['snapFormat'] != snap_configuration.file_format:
        snap_configuration.file_format = conf['snapFormat']
        config_changed = True
        snap_changed = True

    if conf['snapPreTrigger'] != snap_configuration.preTriggerMilliSec:
        snap_configuration.preTriggerMilliSec = conf['snapPreTrigger']
        config_changed = True
        snap_changed = True

    if conf['snapPostTrigger'] != snap_configuration.postTriggerMilliSec:
        snap_configuration.postTriggerMilliSec = conf['snapPostTrigger']
        config_changed = True
        snap_changed = True

    if snap_changed:
        data_sink = DataSink_file.FileOutput(snap_configuration, SnapVariables.SNAPSHOT_DIRECTORY)
        # following may of been changed by the sink on creation
        if data_sink.get_post_trigger_milli_seconds() != snap_configuration.postTriggerMilliSec or \
                data_sink.get_pre_trigger_milli_seconds() != snap_configuration.preTriggerMilliSec:
            snap_configuration.postTriggerMilliSec = data_sink.get_post_trigger_milli_seconds()
            snap_configuration.preTriggerMilliSec = data_sink.get_pre_trigger_milli_seconds()
            SdrVariables.add_to_error(configuration, f"Snap modified to maximum file size of "
                                                     f"{snap_configuration.max_file_size / 1e6}MBytes")
        snap_sink = data_sink

    return data_source, snap_sink, configuration, snap_configuration, config_changed


def send_to_ui(configuration: SdrVariables,
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
    :param time_spectrum: Time of this spectrum in nanoseconds
    :return: array of updated peak powers
    """

    peak_detect = False
    # drop things on the floor if we are told to stop
    if configuration.stop:
        configuration.measured_fps = 0  # not doing anything yet
        configuration.update_count = 0
        current_peak_count = 0
    else:
        configuration.update_count += 1
        one_in_n = int(configuration.sample_rate / (configuration.fps * configuration.fft_size))
        configuration.one_in_n = one_in_n
        if configuration.one_in_n < 1:
            configuration.one_in_n = 1

        # should we try and add to the ui queue
        if configuration.update_count >= one_in_n:
            if current_peak_count == 0:
                configuration.time_first_spectrum = time_spectrum
                peak_powers_since_last_display = powers

            # order the spectral magnitudes, zero in the middle
            display_peaks = np.fft.fftshift(peak_powers_since_last_display)

            # data into the UI queue
            try:
                to_ui_queue.put((configuration.sample_rate, configuration.centre_frequency_hz,
                                 display_peaks, configuration.time_first_spectrum, time_spectrum), block=False)

                # peak since last time is the current powers
                max_peak_count = current_peak_count
                current_peak_count = 0
                configuration.sent_count += 1
                configuration.update_count = 0  # success on putting into queue
            except queue.Full:
                peak_detect = True  # UI can't keep up
        else:
            # nope, so peak detect the fft result instead
            peak_detect = True

        # Is the UI keeping up with how fast we are sending things
        # rather a lot of data may get buffered by the OS or network stack
        seconds = time_spectrum / 1e9
        ack = configuration.ackTime
        if ack == 0:
            ack = seconds
        configuration.ui_delay = round((seconds - ack), 2)

        # if we are more than N seconds behind then reset the fps
        # NOTE on say the pluto which silently drops samples you may have a large gap between samples
        # that gives a low fps as data is not arriving at the correct rate
        if (configuration.ui_delay > 5) and (configuration.measured_fps > 10):
            if configuration.fps != 10:
                configuration.fps_override = True
                configuration.fps = 10  # something safe and sensible
                err_msg = f"UI behind by {configuration.ui_delay}seconds. Defaulting to 10fps"
                # don't give error to the UI as this stops it updating and you end up in a loop
                # configuration.error += err_msg
                logger.info(err_msg)
            peak_detect = True  # UI can't keep up

    if peak_detect:
        if current_peak_count == 0:
            configuration.time_first_spectrum = time_spectrum
        if powers.shape == peak_powers_since_last_display.shape:
            # Record the maximum for each bin, so that ui can show things between display updates
            peak_powers_since_last_display = np.maximum.reduce([powers, peak_powers_since_last_display])
            current_peak_count += 1
        else:
            peak_powers_since_last_display = powers
            current_peak_count = 1
            configuration.time_first_spectrum = time_spectrum
            configuration.update_count = 0
    else:
        peak_powers_since_last_display = np.full(configuration.fft_size, -200)

    return peak_powers_since_last_display, current_peak_count, max_peak_count


def debug_print(sps: float,
                fft_size: int,
                sample_get_time: Ewma,
                process_time: Ewma,
                analysis_time: Ewma,
                reporting_time: Ewma,
                snap_time: Ewma,
                ui_time: Ewma,
                peak_count: float,
                fps: int,
                mfps: float) -> None:
    """
    Various useful profiling prints

    :param sps: Digitisation rate
    :param fft_size: The number of samples per cycle
    :param sample_get_time: How long it took as to receive the digitised samples
    :param process_time: How long we have spent processing the samples
    :param analysis_time: How long we have spent analysing things
    :param reporting_time: How long we have spent reporting things
    :param snap_time: How long we have spent saving snaps
    :param ui_time: How long we have spent telling the ui
    :param peak_count: Count of how many spectrums we are peak detecting on for the UI
    :param fps: requested fps
    :param mfps: measured fps

    :return: None
    """
    data_time = (fft_size / sps)
    total_time = process_time.get_ewma() + analysis_time.get_ewma() + reporting_time.get_ewma() + \
                 snap_time.get_ewma() + ui_time.get_ewma()
    headroom = 100.0 * (data_time - total_time) / data_time
    logger.debug(f'SPS:{sps:.0f}, '
                 f'FFT:{fft_size} '
                 f'{1e6 * data_time:.0f}usec, '
                 f'read:{1e6 * sample_get_time.get_ewma():.0f}usec, '
                 f'process:{1e6 * process_time.get_ewma():.0f}usec, '
                 f'analysis:{1e6 * analysis_time.get_ewma():.0f}usec, '
                 f'report:{1e6 * reporting_time.get_ewma():.0f}usec, '
                 f'snap:{1e6 * snap_time.get_ewma():.0f}usec, '
                 f'ui:{1e6 * ui_time.get_ewma():.0f}usec, '
                 f'total:{1e6 * total_time:.0f}usec, '
                 f'free:{headroom:.0f}%, '
                 f'pc:{peak_count:0.1f}, '
                 f'fps:{fps}, '
                 f'mfps:{mfps}, ')


if __name__ == '__main__':
    main()
