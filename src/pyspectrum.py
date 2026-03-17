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
    * TODO: Timestamps on samples are indeterminate wrt real time, currently well after samples are really generated
    * TODO: When we tune outside the sdr range we dont display the frequency correctly in the UI
    * TODO: Spectrogram does not work with 32768 points
"""

import logging
import multiprocessing
import os
import pathlib
import queue
import signal
import sys
import time
from typing import Tuple, Any

import numpy as np

from dataProcessing import ProcessSamples
from dataSink import DataSink_file
from dataSources import DataSource
from dataSources import DataSourceFactory
from dataSources.SampleFetch import create_sample_fetch, BlockSampleFetch, OverlapSampleFetch
from misc import TimesAndAverages
from misc import PicGenerator
from misc import PluginManager
from misc import Sdr
from misc import Snapper
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

# default logging level
DEFAULT_LOG_LEVEL = logging.INFO

bad_count = 0


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
    sdr_config, snap_config, thumbs_dir = setup()
    logger.info("SpectrumAnalyser started")

    # different python versions may impact us
    if sys.version_info < (3, 7):
        logger.warning(f"Python version nas no support for nanoseconds, current interpreter is V{sys.version}")

    # configuration shared across all processes
    manager = multiprocessing.Manager()
    shared_status = manager.dict()  # contains updates to the UI
    update_queue = multiprocessing.Queue()  # contains updates from the UI

    # initialise our things
    data_source, display, websocket, to_ui_queue, processor, plugin_manager, source_factory, pic_generator, \
        shared_status = initialise(sdr_config, snap_config, thumbs_dir, shared_status, update_queue)

    # the snapshot config
    snap_config.cf = sdr_config.centre_frequency_hz
    snap_config.sps = sdr_config.sample_rate
    data_sink = DataSink_file.FileOutput(snap_config, global_vars.SNAPSHOT_DIRECTORY)

    # Some info on the amount of time to get samples
    expected_samples_receive_time = sdr_config.fft_size / sdr_config.sample_rate
    logger.info(f"SPS: {sdr_config.sample_rate / 1e6:0.3}MHzs "
                f"RBW: {(sdr_config.sample_rate * processor.get_rbw_per_sps()):0.1f}Hz")
    logger.info(f"Samples {sdr_config.fft_size}: {(1000000 * expected_samples_receive_time):.0f}usec")
    logger.info(f"Required FFT per second: {sdr_config.sample_rate / sdr_config.fft_size:.0f}")

    # expected bits/sec on network, 8bits byte, 4 bytes per complex
    bits_sec = 8 * sdr_config.sample_rate * data_source.get_bytes_per_complex_sample() * sdr_config.fft_size
    logger.info(f"Minimum bit rate of input: {(bits_sec / 1e6):.0f}Mbit/sec")

    # Default things before the main loop
    peak_powers_since_last_display = np.full(sdr_config.fft_size, -200)

    # timing things, averages
    times_and_averages = TimesAndAverages.TimesAndAverages()

    time_rx_nsec = 0
    global processing
    samples = None
    config_changed = None
    hop = None

    # do we need to get samples or magnitudes
    fetcher = set_sample_fetcher(data_source, sdr_config)  # fetcher is set if samples required

    # keep processing until told to stop or an error occurs
    while processing:
        loop_start = time.perf_counter()

        if not multiprocessing.active_children():
            processing = False  # we will exit mow as we lost our processes
            continue

        # sync the status and update from UI
        time_start = time.perf_counter()
        if update_queue:
            data_source, data_sink, sdr_config, snap_config, config_changed = sync_state_from_ui(sdr_config,
                                                                                                 snap_config,
                                                                                                 data_source,
                                                                                                 source_factory,
                                                                                                 data_sink,
                                                                                                 thumbs_dir,
                                                                                                 processor,
                                                                                                 shared_status,
                                                                                                 update_queue)
            if config_changed:
                fetcher = set_sample_fetcher(data_source, sdr_config)
        time_end = time.perf_counter()
        times_and_averages.sync_from_ui.average(time_end - time_start)

        ###########################################
        # Get complex samples we will work on
        ######################
        time_start = time.perf_counter()
        if sdr_config.stop or not data_source.connected():
            time.sleep(sdr_config.fft_size / sdr_config.sample_rate)
        else:
            try:
                # do we get complex samples or magnitudes from the source
                if fetcher is None:
                    samples, time_rx_nsec = data_source.read_magnitude_samples(sdr_config.fft_size)
                else:
                    samples, time_rx_nsec, hop = fetcher.get_next_block()

                sdr_config.input_overflows = data_source.get_overflows()

            except ValueError as mm:
                # incorrect number of samples, probably because something closed
                if processing:
                    err_msg = f"Problem with source: {sdr_config.input_source}, {mm}"
                    Sdr.add_to_error(sdr_config, err_msg)
                    logger.error(sdr_config.error)

                    data_source.close()
                    sdr_config.input_source = "null"
                    sdr_config.input_params = ""
                    data_source = sdrStuff.update_source(sdr_config, source_factory)
                    fetcher = set_sample_fetcher(data_source, sdr_config)
                    fill_shared_status_to_ui(shared_status, sdr_config, snap_config)
                    samples = None
        time_end = time.perf_counter()
        times_and_averages.capture_time.average(time_end - time_start)

        ###########################################
        # Get and process the complex/magnitude samples we will work on
        ######################
        if samples is not None:
            # samples will be dtype=np.complex64
            if fetcher is None:
                # samples are magnitudes_squared values
                processor.set_powers(samples, sdr_config.sample_rate, sdr_config.psd, sdr_config.dbm_offset)
            else:
                samples, snap_finished = handle_samples(data_sink, hop, plugin_manager, processor, samples, sdr_config,
                                                        snap_config, time_rx_nsec, times_and_averages)

            ##########################
            # the snap may of changed
            #################
            time_start = time.perf_counter()
            snap_config_changed, data_sink = check_on_snap_config(data_sink, sdr_config, snap_config)

            # Has source or snap changed
            if config_changed or snap_config_changed or snap_finished:
                fill_shared_status_to_ui(shared_status, sdr_config, snap_config)
                config_changed = False

            time_end = time.perf_counter()
            times_and_averages.plugins.average(time_end - time_start)

            ################################
            # Update the UI spectral data
            ###################
            time_start = time.perf_counter()
            peak_powers_since_last_display = send_spectrums_to_ui(sdr_config,
                                                                  to_ui_queue,
                                                                  processor.get_powers(False),
                                                                  peak_powers_since_last_display,
                                                                  time_rx_nsec)
            time_end = time.perf_counter()
            times_and_averages.ui_time.average(time_end - time_start)

        now = time.time()

        time_start = time.perf_counter()
        if update_fps(now, sdr_config, times_and_averages):
            fill_status_fast_to_ui(shared_status, sdr_config, snap_config)

        if now > times_and_averages.debug_time:
            debug_print(sdr_config, times_and_averages)
            times_and_averages.debug_time = now + 60

        update_source_stats(data_source, now, samples, sdr_config, shared_status, times_and_averages)

        if sdr_config.stop or not data_source.connected():
            times_and_averages.loop_time.clear()
        else:
            loop_end = time.perf_counter()
            loop_multiplier = int(100 / (100 - sdr_config.fft_overlap))
            _ = times_and_averages.loop_time.average(loop_multiplier * (loop_end - loop_start))

        time_end = time.perf_counter()
        times_and_averages.misc.average(time_end - time_start)

        # don't spin
        if samples is None:
            sdr_config.loop_cpu_pc = 0
            time.sleep(0.1)

    ####################
    #
    # Exit: clean up
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


def handle_samples(data_sink: DataSink_file, hop: Any | None, plugin_manager: PluginManager, processor: ProcessSamples,
                   samples: complex | Any, sdr_config: Sdr, snap_config: Snapper, time_rx_nsec: int | float | Any,
                   times_and_averages: TimesAndAverages) -> tuple[complex | Any, bool]:
    ##########################
    # save the samples for snapshots
    ##########################
    time_start = time.perf_counter()
    patched_rx_time_nsec = time_rx_nsec + int((hop * 1e9) / sdr_config.sample_rate)
    snap_finished = save_samples(data_sink, samples[-hop:], snap_config, patched_rx_time_nsec, times_and_averages)
    snap_config.currentSizeMbytes = data_sink.get_current_size_mbytes()
    snap_config.expectedSizeMbytes = data_sink.get_size_mbytes()
    time_end = time.perf_counter()
    times_and_averages.save_samples.average(time_end - time_start)

    ##########################
    # dc input offset calculation
    ##########################
    time_start = time.perf_counter()
    if sdr_config.dc_removal != "Off":
        # remove the average value to reduce the dc component
        # weighted towards newest average quickly with previous error less significant than current
        sdr_config.dc_error = sdr_config.dc_error * 0.3 \
                              + np.average(samples) * 0.7
        # check we can write to the array
        if samples.flags.writeable:
            samples -= sdr_config.dc_error
        else:
            # copy it
            samples = samples - sdr_config.dc_error
    time_end = time.perf_counter()
    times_and_averages.dc_offset.average(time_end - time_start)

    ##########################
    # Calculate the spectrum
    #################
    time_start = time.perf_counter()
    processor.process(samples, sdr_config.sample_rate, sdr_config.psd, sdr_config.dbm_offset)
    time_end = time.perf_counter()
    times_and_averages.process_time.average(time_end - time_start)

    ##########################
    # plugins
    #################
    time_start = time.perf_counter()
    call_plugins(plugin_manager, processor, sdr_config, times_and_averages, time_rx_nsec)
    time_end = time.perf_counter()
    times_and_averages.plugins.average(time_end - time_start)
    return samples, snap_finished


def set_sample_fetcher(data_source: DataSource, sdr_config: Sdr) -> BlockSampleFetch | OverlapSampleFetch:
    fetcher = None
    if sdr_config.read_magnitudes:
        try:
            _ = data_source.read_magnitude_samples(sdr_config.fft_size)
        except NotImplementedError:
            logger.error(f"{data_source.get_name()} does not support magnitude samples")
            sdr_config.read_magnitudes = False
            fetcher = create_sample_fetch(data_source, sdr_config)
    else:
        fetcher = create_sample_fetch(data_source, sdr_config)
    return fetcher


def check_on_snap_config(data_sink: DataSink_file.FileOutput, sdr_config: Sdr.Sdr, snap_config: Snapper.Snapper):
    # has underlying sps or cf changed for the snap
    changed = False
    if snap_config.cf != sdr_config.sdr_centre_frequency_hz or \
            snap_config.sps != sdr_config.sample_rate:
        snap_config.cf = sdr_config.sdr_centre_frequency_hz
        snap_config.sps = sdr_config.sample_rate
        snap_config.triggered = False
        snap_config.triggerState = "wait"
        data_sink = DataSink_file.FileOutput(snap_config, global_vars.SNAPSHOT_DIRECTORY)
        snap_config.currentSizeMbytes = 0
        snap_config.expectedSizeMbytes = data_sink.get_size_mbytes()
        changed = True
    return changed, data_sink


def update_source_stats(data_source: DataSource.DataSource, now: float, samples: np.ndarray, sdr_config: Sdr.Sdr,
                        shared_status: dict, times_and_averages: TimesAndAverages.TimesAndAverages):
    # Occasionally check on the source, maybe the gain changed etc
    if now > times_and_averages.config_time:
        sdrStuff.update_source_state(sdr_config, data_source)
        times_and_averages.config_time = now + 1
        data_time = (sdr_config.fft_size / sdr_config.sample_rate)
        sdr_config.loop_cpu_pc = 100.0 * (times_and_averages.loop_time.get_ewma() / data_time)

        # update the input level
        if samples is not None:
            sdr_config.input_level = 100.0 * np.max(np.absolute(samples))
            shared_status['digitiserInputLevel'] = float(sdr_config.input_level)

        # for file inputs, show where we are
        sdr_config.seconds_current = data_source.get_seconds_current()
        shared_status['streamCurrent'] = sdr_config.seconds_current
        sdr_config.seconds_length = data_source.get_seconds_length()
        shared_status['streamLength'] = sdr_config.seconds_length


def update_fps(now: float, sdr_config: Sdr.Sdr, times_and_averages: TimesAndAverages.TimesAndAverages) -> bool:
    # update fps occasionally
    if now > times_and_averages.fps_update_time:
        if (now - sdr_config.time_measure_fps) > 0:
            sdr_config.measured_fps = round(sdr_config.sent_count / (now - sdr_config.time_measure_fps), 1)
        times_and_averages.fps_update_time = now + 1
        sdr_config.time_measure_fps = now
        sdr_config.sent_count = 0
        return True
    return False


def save_samples(data_sink: DataSink_file.FileOutput, samples: np.ndarray, snap_config: Sdr.Sdr,
                 time_rx_nsec: float, times_and_averages: TimesAndAverages.TimesAndAverages) -> bool:
    ##########################
    # Handle snapshots, due to pre-trigger we need to always give the samples
    #################
    time_start = time.perf_counter()
    finished = data_sink.write(snap_config.triggered, samples, time_rx_nsec)

    if finished:
        snap_config.triggered = False
        snap_config.triggerState = "wait"
        snap_config.directory_list = snapStuff.list_snap_files(global_vars.SNAPSHOT_DIRECTORY)

    time_end = time.perf_counter()
    times_and_averages.snap_time.average(time_end - time_start)

    return finished


def call_plugins(plugin_manager, processor: ProcessSamples.ProcessSamples, sdr_config: Sdr.Sdr,
                 times_and_averages: TimesAndAverages.TimesAndAverages, time_rx_nsec: float) -> None:
    ###########################
    # analysis of the spectrum
    #################
    time_start = time.perf_counter()
    results = plugin_manager.call_plugin_method(method="analysis",
                                                args={"powers": processor.get_powers(False),
                                                      "noise_floors": processor.get_long_average(False),
                                                      "reordered": False})
    time_end = time.perf_counter()
    times_and_averages.plugins.average(time_end - time_start)

    if results is not None:
        #####################
        # reporting results, plugin stuff
        #############
        time_start = time.perf_counter()
        if "peaks" in results and len(results["peaks"]) > 0:
            freqs = ProcessSamples.convert_to_frequencies(results["peaks"], sdr_config.sample_rate, sdr_config.fft_size)
            _ = plugin_manager.call_plugin_method(method="report",
                                                  args={"data_samples_time": time_rx_nsec,
                                                        "frequencies": freqs,
                                                        "centre_frequency_hz":
                                                            sdr_config.centre_frequency_hz})
        time_end = time.perf_counter()
        times_and_averages.reporting_time.average(time_end - time_start)


def setup() -> Tuple[Sdr.Sdr, Snapper.Snapper, pathlib.PurePath]:
    """
    Basic things everything else use

    :return:
    """
    setup_logging("SpectrumAnalyser.log")

    # sdr configuration
    configuration = Sdr.Sdr()
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

    # processing
    snap_configuration = setup_snap_config()
    thumbs_dir = set_thumbs_dir()

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
    logger.setLevel(DEFAULT_LOG_LEVEL)


def setup_snap_config() -> Snapper.Snapper:
    # make sure we have the snapshot directory
    snap_configuration = Snapper.Snapper()
    if not os.path.isdir(global_vars.SNAPSHOT_DIRECTORY):
        try:
            os.makedirs(global_vars.SNAPSHOT_DIRECTORY)
        except FileExistsError:
            pass
        except Exception as msg:
            raise ValueError(f"Failed to create snapshot directory, {msg}")
    snap_configuration.directory_list = snapStuff.list_snap_files(global_vars.SNAPSHOT_DIRECTORY)
    return snap_configuration


def set_thumbs_dir() -> pathlib.PurePath:
    # web thumbnail directory
    where = f"{os.path.dirname(__file__)}"
    thumbs_dir = pathlib.PurePath(f"{where}/webUI/webroot/thumbnails")
    if not os.path.isdir(thumbs_dir):
        try:
            os.makedirs(thumbs_dir)
        except FileExistsError:
            pass
        except Exception as msg:
            raise ValueError(f"Failed to create web thumbnails directory, {msg}")
    return thumbs_dir


def initialise(sdr_config: Sdr.Sdr, snap_config: Snapper.Snapper,
               thumbs_dir: pathlib.PurePath, shared_status: dict, update_queue: multiprocessing.Queue) \
        -> Tuple[
            DataSource.DataSource,
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

    :param sdr_config: main config options
    :param snap_config: snapshot config options
    :param thumbs_dir: Where the picture generator will store thumbnails
    :param shared_status: dictionary status shared for multi-processing use
    :param update_queue: queue of items that require updating
    :return: Lots
    """
    try:
        # where we get our input samples from
        factory = DataSourceFactory.DataSourceFactory()
        # check that it is supported
        if sdr_config.input_source not in factory.sources():
            print("Available sources: ", factory.sources())
            raise ValueError(f"Error: Input source type of '{sdr_config.input_source}' is not supported")

        # Queues for UI, control and data are separate when going to ui
        to_ui_queue = multiprocessing.Queue(MAX_TO_UI_QUEUE_DEPTH)

        fill_shared_status_to_ui(shared_status, sdr_config, snap_config)

        display = FlaskInterface.FlaskInterface(to_ui_queue, logger.level, shared_status, update_queue)

        display.start()
        logger.debug(f"Started WebServer, {display}")

        web_socket = WebSocketServer.WebSocketServer(to_ui_queue, logger.level, shared_status['web_socket_port'])
        web_socket.start()
        logger.debug(f"Started WebSocket, {web_socket}")

        # plugins, pass in all the variables as we don't know what the plugin may require
        plugin_manager = PluginManager.PluginManager(plugin_init_arguments=vars(sdr_config))

        data_source = sdrStuff.create_source(sdr_config, factory)
        try:
            sdrStuff.open_source(sdr_config, data_source)

            # allowed sample source
            sdr_config.sample_types = data_source.get_sample_types()
        except ValueError as msg:
            logger.error(f"Connection problem {msg}")
            Sdr.add_to_error(sdr_config, str(msg))

        # The main processor for producing ffts etc
        processor = ProcessSamples.ProcessSamples(sdr_config)
        sdr_config.fft_rbw = processor.get_rbw_per_sps() * sdr_config.sample_rate

        # thumbnail and pic generator process
        pic_generator = PicGenerator.PicGenerator(global_vars.SNAPSHOT_DIRECTORY, thumbs_dir, logger.level)
        pic_generator.start()
        logger.debug(f"Started PicGenerator")

        sdr_config.time_measure_fps = time.time()

        return data_source, display, web_socket, to_ui_queue, processor, \
            plugin_manager, factory, pic_generator, shared_status

    except Exception as msg:
        # exceptions here are fatal
        raise msg


def fill_status_fast_to_ui(shared_status: dict, sdr_config: Sdr.Sdr, snap_config: Snapper.Snapper) -> None:
    # things we want to update faster
    shared_status['digitiserGain'] = sdr_config.gain

    # control stuff
    shared_status['fps'] = ({'set': sdr_config.fps,
                             'measured': sdr_config.measured_fps})
    shared_status['stop'] = sdr_config.stop
    shared_status['delay'] = sdr_config.ui_delay
    shared_status['loopCpuPc'] = sdr_config.loop_cpu_pc
    shared_status['overflows'] = sdr_config.input_overflows
    shared_status['oneInN'] = sdr_config.one_in_n

    # snapshot stuff
    shared_status['snapTriggerState'] = snap_config.triggerState
    shared_status['snapSize'] = ({'current': snap_config.currentSizeMbytes,
                                  'limit': snap_config.expectedSizeMbytes})


def fill_shared_status_to_ui(shared_status: dict, sdr_config: Sdr.Sdr, snap_config: Snapper.Snapper) -> None:
    # Half way house converting over from class containing configuration
    # to a dictionary,so we can use the multiproccessing dictionary between processes

    # source stuff
    # should really be paired up as source, help
    shared_status['sources'] = sdr_config.input_sources_with_helps
    shared_status['source'] = ({'source': sdr_config.input_source,
                                'params': sdr_config.input_params,
                                'connected': sdr_config.source_connected})
    shared_status['errors'] = ""

    # tuning stuff
    shared_status['frequency'] = ({'value': sdr_config.centre_frequency_hz,
                                   'conversion': sdr_config.conversion_frequency_hz})

    # digitiser stuff
    shared_status['digitiserFrequency'] = sdr_config.sdr_centre_frequency_hz
    shared_status['digitiserFormats'] = sdr_config.sample_types
    shared_status['digitiserFormat'] = sdr_config.sample_type
    shared_status['digitiserSampleRate'] = sdr_config.sample_rate
    shared_status['digitiserBandwidth'] = sdr_config.input_bw_hz
    shared_status['digitiserPartsPerMillion'] = sdr_config.ppm_error
    shared_status['digitiserDbmOffset'] = sdr_config.dbm_offset
    shared_status['digitiserGainTypes'] = sdr_config.gain_modes
    shared_status['digitiserGainType'] = sdr_config.gain_mode
    shared_status['digitiserGain'] = sdr_config.gain
    shared_status['digitiserDcRemovals'] = ["Average", "Off"]
    shared_status['digitiserDcRemoval'] = sdr_config.dc_removal
    shared_status['digitiserInputLevel'] = float(sdr_config.input_level)
    shared_status['streamLength'] = sdr_config.seconds_length
    shared_status['streamCurrent'] = sdr_config.seconds_current

    # spectrum stuff
    shared_status['fftSize'] = sdr_config.fft_size
    shared_status['fftOverlaps'] = sdr_config.fft_overlaps
    shared_status['fftOverlap'] = sdr_config.fft_overlap
    shared_status['psd'] = "On" if sdr_config.psd else "Off"
    sdr_config.fft_frame_time = 1e6 * (sdr_config.fft_size / sdr_config.sample_rate)
    shared_status['fftFrameTime'] = sdr_config.fft_frame_time
    shared_status['fftRbw'] = sdr_config.fft_rbw
    # spectrogram does not work with 32768 points
    # 256 points never keeps up due to overheads
    shared_status['fftSizes'] = [512, 1024, 2048, 4096, 8192, 16384]
    shared_status['fftWindows'] = sdr_config.window_types
    shared_status['fftWindow'] = sdr_config.window

    # control stuff
    shared_status['fps'] = ({'set': sdr_config.fps,
                             'measured': sdr_config.measured_fps})
    shared_status['presetFps'] = [1, 5, 10, 20, 40, 80]
    shared_status['stop'] = sdr_config.stop
    shared_status['fpsMeasured'] = 0
    shared_status['delay'] = sdr_config.ui_delay
    shared_status['loopCpuPc'] = sdr_config.loop_cpu_pc
    shared_status['overflows'] = sdr_config.input_overflows
    shared_status['ackTime'] = sdr_config.ackTime
    shared_status['oneInN'] = sdr_config.one_in_n

    shared_status['readMagnitudes'] = "magnitudes" if sdr_config.read_magnitudes else "samples"

    # snapshot stuff
    shared_status['snapTrigger'] = snap_config.triggered
    shared_status['snapTriggerState'] = snap_config.triggerState
    shared_status['snapTriggerSources'] = ['manual', 'off']
    shared_status['snapTriggerSource'] = snap_config.triggerType
    shared_status['snapName'] = snap_config.baseFilename
    shared_status['snapFormats'] = snap_config.file_formats
    shared_status['snapFormat'] = snap_config.file_format
    shared_status['snapPreTrigger'] = snap_config.preTriggerMilliSec
    shared_status['snapPostTrigger'] = snap_config.postTriggerMilliSec
    shared_status['snaps'] = snap_config.directory_list
    shared_status['snapSize'] = ({'current': snap_config.currentSizeMbytes,
                                  'limit': snap_config.expectedSizeMbytes})
    shared_status['snapDelete'] = ""

    # web interface
    shared_status['web_server_port'] = sdr_config.web_port
    shared_status['web_socket_port'] = sdr_config.web_port + 1


def sync_state_from_ui(sdr_config: Sdr.Sdr,
                       snap_config: Snapper.Snapper,
                       data_source: DataSource.DataSource,
                       source_factory,
                       snap_sink: DataSink_file.FileOutput,
                       thumb_dir: pathlib.PurePath,
                       processor: ProcessSamples.ProcessSamples,
                       shared_status: dict,
                       update_queue: multiprocessing.Queue):  # -> Tuple[DataSource, DataSink_file.FileOutput, Sdr, dict, bool]:
    """
    All changes instigated by the UI rest interfaces end up in the shared_update dictionary.
    Once the changes are made we delete the entries in the shared_update dictionary

    :param sdr_config: Sdr configuration
    :param snap_config: Snapper configuration
    :param data_source: the current data source
    :param source_factory: for generating a new source
    :param snap_sink: the sink used for snapshots
    :param thumb_dir: Thumbnail directory
    :param processor: the current processor (fft's)
    :param shared_status: dictionary of the current state for sharing to multi-processing
    :param update_queue: queue of updated items from UI
    :return:
    """
    # -> Tuple[Type[DataSource.DataSource], DataSink_file.FileOutput,
    #                             Sdr, Snapper]:
    # conf  multiprocessing dictionary

    snap_changed = False
    config_changed = False
    while update_queue.qsize() > 0:
        try:
            msg = update_queue.get()
            message_name = msg['type']
            message_value = msg['set']
            # print(message_name, message_value)

            if message_name == 'source':
                source = message_value
                params = msg['params']
                if params == '?' or \
                        source != sdr_config.input_source or \
                        (params != sdr_config.input_params):
                    logger.debug(f"changing source from "
                                 f"'{sdr_config.input_source}' '{sdr_config.input_params}' to "
                                 f"'{source}' '{params}'")
                    data_source = sdrStuff.change_source(data_source, source_factory, sdr_config, source, params)
                    if source == 'file':
                        # May need to configure things from the filename
                        if data_source.has_meta_data():
                            shared_status['digitiserSampleRate'] = sdr_config.sample_rate
                            shared_status['frequency'] = ({'value': sdr_config.centre_frequency_hz, 'conversion': 0})
                            shared_status['digitiserFrequency'] = sdr_config.centre_frequency_hz
                            shared_status['digitiserFormat'] = sdr_config.sample_type
                    Sdr.add_to_error(sdr_config, data_source.get_and_reset_error())
                    shared_status['errors'] = Sdr.get_and_reset_error(sdr_config)
                    # if we change src to null make sure we don't try again immediately
                    shared_status['source'] = ({'source': data_source.get_name(),
                                                'params': data_source.get_parameters(),
                                                'connected': sdr_config.source_connected})
                    sdr_config.input_params = data_source.get_parameters()
                    sdr_config.input_overflows = 0
                    config_changed = True
                    snap_changed = True

            if message_name == 'readMagnitudes':
                mags = True if message_value == "magnitudes" else False
                if mags != sdr_config.read_magnitudes:
                    sdr_config.read_magnitudes = mags
                    config_changed = True

            if message_name == 'fps':
                if message_value != sdr_config.fps:
                    sdr_config.fps = message_value
                    fudge = (100 - sdr_config.fft_overlap) / 100
                    sdr_config.one_in_n = int(sdr_config.sample_rate / (fudge * sdr_config.fps * sdr_config.fft_size))

            if message_name == 'ackTime':
                if message_value != sdr_config.ackTime:
                    sdr_config.ackTime = message_value

            if message_name == 'frequency':
                freq = message_value
                conversion = msg['conversion']
                if freq != sdr_config.centre_frequency_hz \
                        or conversion != sdr_config.conversion_frequency_hz:
                    new_cf = freq
                    new_dc = conversion
                    new_sdr_cf = new_cf - new_dc  # works for +ve and -ve conversions
                    data_source.set_centre_frequency_hz(new_sdr_cf)
                    Sdr.add_to_error(sdr_config, data_source.get_and_reset_error())

                    # update our sdr frequency from what the sdr did
                    sdr_config.sdr_centre_frequency_hz = data_source.get_centre_frequency_hz()
                    sdr_config.centre_frequency_hz = sdr_config.sdr_centre_frequency_hz + new_dc
                    sdr_config.conversion_frequency_hz = new_dc
                    config_changed = True

            if message_name == 'digitiserBandwidth':
                if message_value != sdr_config.input_bw_hz:
                    data_source.set_bandwidth_hz(message_value)
                    Sdr.add_to_error(sdr_config, data_source.get_and_reset_error())
                    sdr_config.input_bw_hz = data_source.get_bandwidth_hz()
                    config_changed = True

            if message_name == 'digitiserPartsPerMillion':
                if message_value != sdr_config.ppm_error:
                    data_source.set_ppm(float(message_value))
                    Sdr.add_to_error(sdr_config, data_source.get_and_reset_error())
                    sdr_config.ppm_error = data_source.get_ppm()
                    config_changed = True

            if message_name == 'digitiserDcRemoval':
                sdr_config.dc_removal = message_value
                sdr_config.dc_error = complex(0, 0)
                config_changed = True

            if message_name == 'digitiserDbmOffset':
                if message_value != sdr_config.dbm_offset:
                    sdr_config.dbm_offset = (float(message_value))
                    config_changed = True

            if message_name == 'digitiserSampleRate':
                if message_value != sdr_config.sample_rate:
                    data_source.set_sample_rate_sps(message_value)
                    Sdr.add_to_error(sdr_config, data_source.get_and_reset_error())
                    sdr_config.sample_rate = data_source.get_sample_rate_sps()
                    sdr_config.input_bw_hz = data_source.get_bandwidth_hz()  # some sources over-ride bw when setting sps
                    sdr_config.input_overflows = 0
                    fudge = (100 - sdr_config.fft_overlap) / 100
                    sdr_config.one_in_n = int(sdr_config.sample_rate / (fudge * sdr_config.fps * sdr_config.fft_size))
                    config_changed = True

            if message_name == 'digitiserFormat':
                if message_value != sdr_config.sample_type:
                    data_source.set_sample_type(message_value)
                    Sdr.add_to_error(sdr_config, data_source.get_and_reset_error())
                    sdr_config.sample_type = data_source.get_sample_type()
                    config_changed = True
                    shared_status['digitiserFormat'] = sdr_config.sample_type

            if message_name == 'stop':
                if message_value != sdr_config.stop:
                    sdr_config.stop = message_value
                    config_changed = True

            if message_name == 'fftWindow':
                if message_value != sdr_config.window:
                    processor.set_window(message_value)
                    sdr_config.window = processor.get_window()
                    sdr_config.fft_rbw = processor.get_rbw_per_sps() * sdr_config.sample_rate
                    config_changed = True

            if message_name == 'fftSize':
                if message_value != sdr_config.fft_size:
                    sdr_config.fft_size = message_value
                    processor.set_fft_size(sdr_config.fft_size)
                    fudge = (100 - sdr_config.fft_overlap) / 100
                    sdr_config.one_in_n = int(sdr_config.sample_rate / (fudge * sdr_config.fps * sdr_config.fft_size))
                    sdr_config.fft_rbw = processor.get_rbw_per_sps() * sdr_config.sample_rate
                    config_changed = True

            if message_name == 'fftOverlap':
                if message_value != sdr_config.fft_overlap:
                    sdr_config.fft_overlap = message_value
                    fudge = (100 - sdr_config.fft_overlap) / 100  # account for more spectrums
                    sdr_config.one_in_n = int(sdr_config.sample_rate / (fudge * sdr_config.fps * sdr_config.fft_size))
                    config_changed = True

            if message_name == 'psd':
                psd = True if message_value == "On" else False
                if psd != sdr_config.psd:
                    sdr_config.psd = psd
                    config_changed = True

            if message_name == 'digitiserGain':
                if message_value != sdr_config.gain:
                    sdr_config.gain = message_value
                    data_source.set_gain(sdr_config.gain)
                    Sdr.add_to_error(sdr_config, data_source.get_and_reset_error())
                    sdr_config.gain = data_source.get_gain()
                    config_changed = True

            if message_name == 'digitiserGainType':
                if message_value != sdr_config.gain_mode:
                    sdr_config.gain_mode = message_value
                    data_source.set_gain_mode(sdr_config.gain_mode)
                    Sdr.add_to_error(sdr_config, data_source.get_and_reset_error())
                    sdr_config.gain_mode = data_source.get_gain_mode()
                    config_changed = True

            if message_name == 'snapDelete':
                if message_value != "":
                    snapStuff.delete_file(message_value, thumb_dir)
                    shared_status['snapDelete'] = ""
                    snap_config.directory_list = snapStuff.list_snap_files(global_vars.SNAPSHOT_DIRECTORY)
                    fudge = (100 - sdr_config.fft_overlap) / 100
                    sdr_config.one_in_n = int(sdr_config.sample_rate / (fudge * sdr_config.fps * sdr_config.fft_size))
                    config_changed = True

            if message_name == 'snapTrigger':
                if message_value and snap_config.triggerState != "triggered":
                    if snap_config.triggerType == "manual":
                        snap_config.triggered = True
                        snap_config.triggerState = "triggered"
                        config_changed = True

            if message_name == 'snapTriggerSource':
                if message_value != snap_config.triggerType:
                    snap_config.triggerType = message_value
                    config_changed = True

            if message_name == 'snapName':
                if message_value != snap_config.baseFilename:
                    snap_config.baseFilename = message_value
                    config_changed = True
                    snap_changed = True

            if message_name == 'snapFormat':
                if message_value != snap_config.file_format:
                    snap_config.file_format = message_value
                    config_changed = True
                    snap_changed = True

            if message_name == 'snapPreTrigger':
                if message_value != snap_config.preTriggerMilliSec:
                    snap_config.preTriggerMilliSec = message_value
                    config_changed = True
                    snap_changed = True

            if message_name == 'snapPostTrigger':
                if message_value != snap_config.postTriggerMilliSec:
                    snap_config.postTriggerMilliSec = message_value
                    config_changed = True
                    snap_changed = True

            if snap_changed:
                snap_config.sps = data_source.get_sample_rate_sps()
                data_sink = DataSink_file.FileOutput(snap_config, global_vars.SNAPSHOT_DIRECTORY)
                fudge = (100 - sdr_config.fft_overlap) / 100
                sdr_config.one_in_n = int(sdr_config.sample_rate / (fudge * sdr_config.fps * sdr_config.fft_size))

                # following may of been changed by the sink on creation
                if data_sink.get_post_trigger_milli_seconds() != snap_config.postTriggerMilliSec or \
                        data_sink.get_pre_trigger_milli_seconds() != snap_config.preTriggerMilliSec:
                    snap_config.postTriggerMilliSec = data_sink.get_post_trigger_milli_seconds()
                    snap_config.preTriggerMilliSec = data_sink.get_pre_trigger_milli_seconds()
                    Sdr.add_to_error(sdr_config, f"Snap modified to maximum file size of "
                                                 f"{snap_config.max_file_size / 1e6}MBytes")
                snap_sink = data_sink

        except Exception as msg:
            logging.exception("sync_state_from_ui")
            logger.error(f"sync_state_from_ui() error '{msg}' from something in {msg}")

    return data_source, snap_sink, sdr_config, snap_config, config_changed


def send_spectrums_to_ui(sdr_config: Sdr.Sdr,
                         to_ui_queue: multiprocessing.Queue,
                         powers: np.ndarray,
                         peak_powers_since_last_display: np.ndarray,
                         time_spectrum: float) -> np.ndarray:
    """
    Send data to the queue used for talking to the ui processes

    :param sdr_config: Our programme state variables
    :param to_ui_queue: The queue used for talking to the UI process
    :param powers: The powers of the spectrum bins
    :param peak_powers_since_last_display: The powers since we last updated the UI
    :param time_spectrum: Time of this spectrum in nanoseconds
    :return: array of updated peak powers
    """
    peak_detect = False
    if sdr_config.stop:
        # drop things on the floor if we are told to stop
        sdr_config.measured_fps = 0  # not doing anything yet
        sdr_config.update_count = 0
    else:
        if powers is None:
            return peak_powers_since_last_display

        if sdr_config.one_in_n < 1:
            sdr_config.one_in_n = 1

        # should we try and add to the ui queue
        if sdr_config.update_count >= sdr_config.one_in_n:
            # Is the UI keeping up with how fast we are sending things
            # rather a lot of data may get buffered by the OS or network stack
            seconds = sdr_config.time_first_spectrum / 1e9
            ack = sdr_config.ackTime  # should be the last spectrum shown
            if ack != 0:
                sdr_config.ui_delay = round((seconds - ack), 2)
                if sdr_config.ui_delay > 2:
                    # Maybe stuck ack time as the UI is not getting any spectrums
                    if sdr_config.update_count < (2 * sdr_config.one_in_n):
                        peak_detect = True  # UI can't keep up
                    else:
                        sdr_config.time_first_spectrum = time_spectrum
                        peak_powers_since_last_display = powers
                        sdr_config.update_count = 1

            if not peak_detect:
                # order the spectral magnitudes, zero in the middle
                display_peaks = np.fft.fftshift(peak_powers_since_last_display)

                # data into the UI queue
                try:
                    to_ui_queue.put((sdr_config.sample_rate, sdr_config.centre_frequency_hz,
                                     display_peaks, sdr_config.time_first_spectrum, time_spectrum + 1), block=True)

                    # peak since last time is the current powers
                    sdr_config.sent_count += 1
                    sdr_config.update_count = 0  # success on putting into queue
                except queue.Full:
                    peak_detect = True  # UI can't keep up
        else:
            # nope, so peak detect the fft result instead
            peak_detect = True

    if peak_detect:
        if sdr_config.update_count == 0:
            sdr_config.time_first_spectrum = time_spectrum
            peak_powers_since_last_display = powers
        else:
            if powers.shape == peak_powers_since_last_display.shape:
                # Record the maximum (peak) for each bin
                peak_powers_since_last_display = np.maximum.reduce([powers, peak_powers_since_last_display])
            else:
                peak_powers_since_last_display = powers
                sdr_config.time_first_spectrum = time_spectrum
                sdr_config.update_count = 0
        sdr_config.update_count += 1

    return peak_powers_since_last_display


def debug_print(sdr_config: Sdr.Sdr, times_and_averages: TimesAndAverages.TimesAndAverages) -> None:
    """
    Various useful profiling prints

    :return: None
    """
    data_time = (sdr_config.fft_size / sdr_config.sample_rate)
    loop_cpu_pc = 100.0 * (times_and_averages.loop_time.get_ewma() / data_time)

    total = times_and_averages.process_time.get_ewma()
    total += times_and_averages.capture_time.get_ewma()
    total += times_and_averages.reporting_time.get_ewma()
    total += times_and_averages.reporting_time.get_ewma()
    total += times_and_averages.snap_time.get_ewma()
    total += times_and_averages.ui_time.get_ewma()
    total += times_and_averages.sync_from_ui.get_ewma()
    total += times_and_averages.save_samples.get_ewma()
    total += times_and_averages.dc_offset.get_ewma()
    total += times_and_averages.plugins.get_ewma()
    total += times_and_averages.snap_config.get_ewma()
    total += times_and_averages.misc.get_ewma()

    logger.debug(f'SPS:{sdr_config.sample_rate:.0f}, '
                 f'FFT:{sdr_config.fft_size} '
                 f'{1e6 * data_time:.0f}usec, '
                 f'overlap: {sdr_config.fft_overlap}%, '
                 f'loop:{(times_and_averages.loop_time.get_ewma() * 1000000):.0f}usec {loop_cpu_pc:.0f}%, '
                 f'fps/mfps:{sdr_config.fps}/{sdr_config.measured_fps}, '
                 f'total:{1e6 * total:.0f}us: '
                 f'read:{1e6 * times_and_averages.capture_time.get_ewma():.0f}us, '
                 f'proc:{1e6 * times_and_averages.process_time.get_ewma():.0f}us, '
                 f'report:{1e6 * times_and_averages.reporting_time.get_ewma():.0f}us, '
                 f'snap:{1e6 * times_and_averages.snap_time.get_ewma():.0f}us, '
                 f'from_ui:{1e6 * times_and_averages.sync_from_ui.get_ewma():.0f}us, '
                 f'save:{1e6 * times_and_averages.save_samples.get_ewma():.0f}us, '
                 f'dc:{1e6 * times_and_averages.dc_offset.get_ewma():.0f}us, '
                 f'plugins:{1e6 * times_and_averages.plugins.get_ewma():.0f}us, '
                 f'config:{1e6 * times_and_averages.snap_config.get_ewma():.0f}us, '
                 f'misc:{1e6 * times_and_averages.misc.get_ewma():.0f}us, '
                 f'ui:{1e6 * times_and_averages.ui_time.get_ewma():.0f}us'
                 )


if __name__ == '__main__':
    main()
