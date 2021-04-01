#!/bin/python3
"""
Provide a basic spectrum analyser for digitised complex samples

## TODOs, in no particular order
    * TODO: Convert inputs to streaming interfaces.
    * TODO: Drop receivers?
    * TODO: Add a seconds marker to the bottom (left) of the spectrogram
    * TODO: Plugin for triggering snapshot on fft bin power, with masks
    * TODO: On web interface update just the rows that changed on the configuration table
    * TODO: On web interface config and snap tables change to just update the current not the new cells
    * TODO: On web interface is there a way to update the help when a different source is selected
    * TODO: On web interface why don't the interval functions for updating things work
    * TODO: Generic way to handle data sources with unique parameters
    * TODO: UI responsiveness is tied to data arriving, should be independent of arriving spectrum data
    * TODO: Favourites tab for source, freq, rate etc
"""

import json
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
from misc import sdrStuff
from misc import snapStuff
from webUI import WebServer
from misc import global_vars

processing = True  # global to be set to False from ctrl-c
# old_one_in_n = 0  # for debugging fps

# We will use separate log files for each process, main/webserver/websocket
# Perceived wisdom is to use a logging server in multiprocessing environments, maybe in the future
logger = logging.getLogger("spectrum_logger")  # a name we use to find this logger

MAX_TO_UI_QUEUE_DEPTH = 10  # low for low latency
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
    try:
        os.mkdir(pathlib.PurePath(os.path.dirname(__file__), global_vars.log_dir))
    except FileExistsError:
        pass
    except Exception as msg:
        print(f"Failed to create logging directory, {msg}")
        exit(1)

    log_file = pathlib.PurePath(os.path.dirname(__file__), global_vars.log_dir, "SpectrumAnalyser.log")
    try:
        # don't use %Z for timezone as some say 'GMT' or 'GMT standard time'
        logging.basicConfig(format='%(asctime)s,%(levelname)s:%(name)s:%(module)s:%(message)s',
                            datefmt="%Y-%m-%d %H:%M:%S UTC",
                            filemode='w',
                            filename=log_file)
    except Exception as msg:
        print(f"Failed to create logger for main, {msg}")
        exit(1)

    logging.Formatter.converter = time.gmtime  # GMT/UTC timestamps on logging
    logger.setLevel(logging.WARN)

    logger.info("SpectrumAnalyser started")

    # different python versions may impact us
    if sys.version_info < (3, 7):
        logger.warning(f"Python version nas no support for nanoseconds, current interpreter is V{sys.version}")

    global processing
    signal.signal(signal.SIGINT, signal_handler)

    # directories we need
    try:
        os.mkdir(pathlib.PurePath(os.path.dirname(__file__), "webUI", "webroot", "thumbnails"))
    except FileExistsError:
        pass
    except Exception as msg:
        print(f"Failed to create web thumbnails directory, {msg}")
        exit(1)

    try:
        os.mkdir(pathlib.PurePath(os.path.dirname(__file__), global_vars.snapshot_dir))
    except FileExistsError:
        pass
    except Exception as msg:
        print(f"Failed to create snapshot directory, {msg}")
        exit(1)

    # default config and setup
    configuration, snap_configuration, thumbs_dir = setup()

    # all our things
    data_source, display, to_ui_queue, to_ui_control_queue, from_ui_queue, processor, \
        plugin_manager, source_factory, pic_generator = initialise(configuration, thumbs_dir)

    # the snapshot config
    snap_configuration.cf = configuration.real_centre_frequency_hz
    snap_configuration.sps = configuration.sample_rate
    data_sink = DataSink_file.FileOutput(snap_configuration, SnapVariables.SNAPSHOT_DIRECTORY)

    # Some info on the amount of time to get samples
    expected_samples_receive_time = configuration.fft_size / configuration.sample_rate
    logger.info(f"SPS: {configuration.sample_rate / 1e6:0.3}MHzs "
                f"RBW: {(configuration.sample_rate / (configuration.fft_size * 1e3)):0.1f}kHz")
    logger.info(f"Samples {configuration.fft_size}: {(1000000 * expected_samples_receive_time):.0f}usec")
    logger.info(f"Required FFT per second: {configuration.sample_rate / configuration.fft_size:.0f}")

    # expected bits/sec on network, 8bits byte, 4 bytes per complex
    bits_sec = configuration.sample_rate * 8 * data_source.get_bytes_per_sample()
    logger.info(f"Minimum bit rate of input: {(bits_sec / 1e6):.0f}Mbit/sec")

    # Default things before the main loop
    peak_powers_since_last_display = np.full(configuration.fft_size, -200)
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
    while processing:

        if not multiprocessing.active_children():
            processing = False  # we will exit mow as we lost our processes

        # if there is a control message then it may change whats happening
        data_source, data_sink = handle_from_ui_queue(configuration, snap_configuration,
                                                      to_ui_control_queue, from_ui_queue,
                                                      data_source, source_factory, data_sink,
                                                      thumbs_dir, processor)

        ###########################################
        # Get and process the complex samples we will work on
        ######################
        try:
            time_start = time.perf_counter()
            samples, time_rx_nsec = data_source.read_cplx_samples()
            time_end = time.perf_counter()

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
                    snap_configuration.snapState = "stop"
                    snap_configuration.directory_list = snapStuff.list_snap_files(SnapVariables.SNAPSHOT_DIRECTORY)

                snap_configuration.currentSizeMbytes = data_sink.get_current_size_mbytes()
                snap_configuration.expectedSizeMbytes = data_sink.get_size_mbytes()

                time_end = time.perf_counter()
                snap_time.average(time_end - time_start)

                time_start = time.perf_counter()

                # has underlying sps or cf changed for the snap
                if snap_configuration.cf != configuration.real_centre_frequency_hz or \
                        snap_configuration.sps != configuration.sample_rate:
                    snap_configuration.cf = configuration.real_centre_frequency_hz
                    snap_configuration.sps = configuration.sample_rate
                    snap_configuration.triggered = False
                    snap_configuration.triggerState = "wait"
                    snap_configuration.snapState = "stop"
                    data_sink = DataSink_file.FileOutput(snap_configuration, SnapVariables.SNAPSHOT_DIRECTORY)
                    snap_configuration.currentSizeMbytes = 0
                    snap_configuration.expectedSizeMbytes = data_sink.get_size_mbytes()

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
                configuration.error += err_msg
                logger.error(configuration.error)

        now = time.time()
        if now > fps_update_time:
            if (now - configuration.time_measure_fps) > 0:
                configuration.measured_fps = round(configuration.sent_count / (now - configuration.time_measure_fps), 1)
            fps_update_time = now + 2
            configuration.time_measure_fps = now
            configuration.sent_count = 0

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

    if multiprocessing.active_children():
        logger.debug(f"Shutting down child processes, {multiprocessing.active_children()}")
        # belt and braces
        display.terminate()
        display.shutdown()
        display.join()
        pic_generator.terminate()
        pic_generator.shutdown()
        pic_generator.join()

    if to_ui_queue:
        while not to_ui_queue.empty():
            _ = to_ui_queue.get()
        logger.debug("SpectrumAnalyser to_ui_queue empty")

    if to_ui_control_queue:
        while not to_ui_control_queue.empty():
            _ = to_ui_control_queue.get()
        logger.debug("SpectrumAnalyser to_ui_control_queue empty")

    logger.error("SpectrumAnalyser exit")


def setup() -> Tuple[SdrVariables.SdrVariables, SnapVariables.SnapVariables, pathlib.PurePath]:
    """
    Basic things everything else use

    :return:
    """
    # sdr configuration
    configuration = SdrVariables.SdrVariables()
    commandLine.parse_command_line(configuration, logger)

    # check we have a valid input sample type
    if configuration.sample_type not in DataSource.supported_data_types:
        logger.critical(f'Illegal sample type of {configuration.sample_type} selected')
        quit()

    # get all the sources available to us
    configuration.input_sources = DataSourceFactory.DataSourceFactory().sources()
    configuration.input_sources_web_helps = DataSourceFactory.DataSourceFactory().web_help_strings()

    # windowing
    configuration.window_types = ProcessSamples.get_windows()
    configuration.window = configuration.window_types[0]

    # snapshot config
    snap_configuration = SnapVariables.SnapVariables()
    if not os.path.isdir(SnapVariables.SNAPSHOT_DIRECTORY):
        os.makedirs(SnapVariables.SNAPSHOT_DIRECTORY)
    snap_configuration.directory_list = snapStuff.list_snap_files(SnapVariables.SNAPSHOT_DIRECTORY)

    # web thumbnail directory
    where = f"{os.path.dirname(__file__)}"
    thumbs_dir = pathlib.PurePath(f"{where}/webUI/webroot/thumbnails")
    if not os.path.isdir(thumbs_dir):
        os.makedirs(thumbs_dir)

    return configuration, snap_configuration, thumbs_dir


def initialise(configuration: SdrVariables, thumbs_dir: pathlib.PurePath) -> Tuple[Type[DataSource.DataSource],
                                                                                   WebServer.WebServer,
                                                                                   multiprocessing.Queue,
                                                                                   multiprocessing.Queue,
                                                                                   multiprocessing.Queue,
                                                                                   ProcessSamples.ProcessSamples,
                                                                                   PluginManager.PluginManager,
                                                                                   DataSourceFactory.DataSourceFactory,
                                                                                   PicGenerator.PicGenerator]:
    """
    Initialise everything we need

    :param configuration: How we will be configured
    :param thumbs_dir: Where the picture generator will store thumbnails
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
        to_ui_control_queue = multiprocessing.Queue(MAX_TO_UI_QUEUE_DEPTH)
        # queue from ui only has control
        from_ui_queue = multiprocessing.Queue(MAX_FROM_UI_QUEUE_DEPTH)

        display = WebServer.WebServer(to_ui_queue, to_ui_control_queue, from_ui_queue,
                                      logger.level, configuration.web_port)
        display.start()
        logger.debug(f"Started WebServer, {display}")

        # plugins, pass in all the variables as we don't know what the plugin may require
        plugin_manager = PluginManager.PluginManager(plugin_init_arguments=vars(configuration))

        data_source = sdrStuff.create_source(configuration, factory)
        try:
            sdrStuff.open_source(configuration, data_source)

            # allowed sample source
            configuration.sample_types = data_source.get_sample_types()
        except ValueError as msg:
            logger.error(f"Connection problem {msg}")
            configuration.error += str(msg)

        # The main processor for producing ffts etc
        processor = ProcessSamples.ProcessSamples(configuration)

        # thumbnail and pic generator process
        pic_generator = PicGenerator.PicGenerator(SnapVariables.SNAPSHOT_DIRECTORY, thumbs_dir, logger.level)
        pic_generator.start()
        logger.debug(f"Started PicGenerator")

        configuration.time_measure_fps = time.time()

        return data_source, display, to_ui_queue, to_ui_control_queue, \
               from_ui_queue, processor, plugin_manager, factory, pic_generator

    except Exception as msg:
        # exceptions here are fatal
        raise msg


def handle_from_ui_queue(configuration: SdrVariables,
                         snap_configuration: SnapVariables,
                         to_ui_control_queue: multiprocessing.Queue,
                         from_ui_queue: multiprocessing.Queue,
                         data_source,
                         source_factory,
                         snap_sink,
                         thumb_dir: pathlib.PurePath,
                         processor: ProcessSamples) -> Tuple[Type[DataSource.DataSource], DataSink_file.FileOutput]:
    """
    Check the control queue for messages and handle them

    :param configuration: the current configuration
    :param snap_configuration: the current snapshot config
    :param to_ui_control_queue: The queue used for talking to the UI process
    :param from_ui_queue: The queue to check on
    :param data_source:
    :param source_factory:
    :param snap_sink:
    :param thumb_dir:
    :param processor:
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
            elif new_config['type'] == "ack":
                # time of last UI processed data
                configuration.ack = int(new_config['value'])
            elif new_config['type'] == "stop":
                configuration.stop = int(new_config['value'])
            elif new_config['type'] == "snapUpdate":
                snap_sink = snapStuff.handle_snap_message(snap_sink,
                                                          snap_configuration,
                                                          new_config,
                                                          configuration,
                                                          thumb_dir)
            elif new_config['type'] == "sdrUpdate":
                # we may be directed to change the source
                data_source = sdrStuff.handle_sdr_message(configuration,
                                                          new_config,
                                                          data_source,
                                                          source_factory,
                                                          processor)
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
    :param time_spectrum: Time of this spectrum in nano seconds
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
            peak_detect = True

        # Is the UI keeping up with how fast we are sending things
        # rather a lot of data may get buffered by the OS or network stack
        seconds = time_spectrum / 1e9
        ack = configuration.ack
        if ack == 0:
            ack = seconds
        configuration.ui_delay = round((seconds - ack), 2)

        # if we are more than N seconds behind then reset the fps
        # NOTE on say the pluto which silently drops samples you may have a large gap between samples
        # that gives a low fps as data is not arriving at the correct rate
        if (configuration.ui_delay > 5) and (configuration.measured_fps > 10):
            if configuration.fps != 10:
                configuration.fps = 10  # something safe and sensible
                err_msg = f"UI behind by {configuration.ui_delay}seconds. Defaulting to 10fps"
                # don't give error to the UI as this stops it updating and you end up in a loop
                # configuration.error += err_msg
                logger.info(err_msg)
            peak_detect = True  # UI can't keep up

        # global old_one_in_n
        # if one_in_n != old_one_in_n:
        #     print(f"1inN {one_in_n}, "
        #           f"reqFps {configuration.fps}, "
        #           f"fft {configuration.fft_size}, "
        #           f"sps {configuration.sample_rate}, "
        #           f"realFps {int(configuration.sample_rate / configuration.fft_size)}, "
        #           f"delay {diff}seconds")
        #     old_one_in_n = one_in_n

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
