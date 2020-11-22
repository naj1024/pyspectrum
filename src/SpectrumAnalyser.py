#!/bin/python3
"""
Provide a basic spectrum analyser for digitised complex samples

"""

import argparse
import time
import multiprocessing
import signal
import textwrap
import queue
import logging
from typing import Tuple
import random
import sys
import json

import numpy as np

from dataSources import DataSourceFactory
from dataSources import DataSource
from dataProcessing import ProcessSamples
from misc import Ewma
from misc import PluginManager
from misc import Variables
from webUI import WebServer

processing = True  # global to be set to False from ctrl-c

# we will use separate log files for each process, main/webserver/websocket
# TODO: Perceived wisdom is to use a logging server in multiprocessing environments
logger = None

MAX_UI_QUEUE_DEPTH = 4  # low for low latency, a high value will give a burst of contiguous spectrums at the start


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
    logger = logging.getLogger('spectrum_logger')
    # don't use %Z for timezone as some say 'GMT' or 'GMT standard time'
    logging.basicConfig(format='%(asctime)s,%(levelname)s:%(name)s:%(module)s:%(message)s',
                        datefmt="%Y-%m-%d %H:%M:%S UTC",
                        filemode='w',
                        filename="spec.log")
    logging.Formatter.converter = time.gmtime  # GMT/UTC timestamps on logging
    logger.setLevel(logging.INFO)

    if sys.version_info < (3, 7):
        logger.warning(f"Python version means sample timings will be course, python V{sys.version}")

    logger.info("SpectrumAnalyser starting")

    global processing
    signal.signal(signal.SIGINT, signal_handler)

    configuration = Variables.Variables()
    parse_command_line(configuration)

    # check we have a valid input sample type
    if configuration.sample_type not in DataSource.supported_data_types:
        logger.critical(f'Illegal sample type of {configuration.sample_type} selected')
        quit()

    configuration.input_sources = DataSourceFactory.DataSourceFactory().sources()
    configuration.input_sources_web_helps = DataSourceFactory.DataSourceFactory().web_help_strings()

    # configure us
    data_source, display, ui_queue, control_queue, processor, plugin_manager, source_factory = initialise(
        configuration)

    # allowed sample types
    configuration.sample_types = data_source.get_sample_types()

    # expected time to get samples
    expected_samples_receive_time = configuration.fft_size / configuration.sample_rate
    logger.info(f"SPS: {configuration.sample_rate / 1e6:0.3}MHz "
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
    reconnect_count = 0

    # keep processing until told to stop or an error occurs
    # loop_count = 0
    peak_average = Ewma.Ewma(0.1)
    current_peak_count = 0
    max_peak_count = 0
    while processing:

        if not multiprocessing.active_children():
            processing = False  # we will exit mow

        # TODO: Testing changing parameters on the fly
        # loop_count += 1
        # if loop_count == 9000:
        #     print("Changing source")
        #     configuration.centre_frequency_hz = 153.2e6
        #     configuration.sample_rate = 2e6
        #     configuration.fft_size = 4096
        #     # input source has to be changed, or in the future updated to new parameters
        #     data_source.close()
        #     data_source = create_source(configuration, source_factory)
        #     peak_powers_since_last_display = np.full(configuration.fft_size, -200)

        # if there is a control message then it may change what the front end is doing
        data_source = handle_control_queue(configuration, ui_queue, control_queue, data_source, source_factory)

        ###########################################
        # Get the complex samples we will work on
        ######################
        try:
            data_samples_perf_time_start = time.perf_counter()
            samples, time_rx = data_source.read_cplx_samples()
            data_samples_perf_time_end = time.perf_counter()
            _ = sample_get_time.average(data_samples_perf_time_end - data_samples_perf_time_start)
            if samples is None:
                logger.error("No samples")
                time.sleep(1)
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
                                                          args={"data_samples_time": time_rx,
                                                                "frequencies": freqs,
                                                                "centre_frequency_hz": configuration.centre_frequency_hz})

                ##########################
                # Update the UI
                #################
                peak_powers_since_last_display, current_peak_count, max_peak_count = \
                    update_ui(configuration,
                              ui_queue,
                              processor.get_powers(False),
                              peak_powers_since_last_display,
                              current_peak_count,
                              max_peak_count,
                              time_rx)

                # average of number of count of spectrums between UI updates
                peak_average.average(max_peak_count)

                complete_process_time_end = time.perf_counter()  # time for everything but data get
                process_time.average(complete_process_time_end - complete_process_time_start)

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
                            reconnect_count,
                            peak_average.get_ewma(),
                            configuration.fps,
                            configuration.measured_fps,
                            configuration.oneInN)
                debug_time = now + 6

            if now > config_time:
                # Send the current configuration to the UI
                ui_queue.put((configuration.make_json(), None, None, None, None, None))
                configuration.error = ""  # reset any error we are reporting
                config_time = now + 10

        except ValueError:
            # incorrect number of samples, probably because something closed
            while not data_source.connected() and processing:
                try:
                    data_source.reconnect()
                    reconnect_count += 1
                except Exception as msg:
                    logger.debug(msg)

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

    if ui_queue:
        # ui_queue.close()
        while not ui_queue.empty():
            _ = ui_queue.get()
        logger.debug("SpectrumAnalyser ui_queue empty")

    logger.error("SpectrumAnalyser exit")


# Problem defining what we return, DataSource can be many different things
# def initialise(configuration: Variables) -> Tuple[DataSource, DisplayProcessor, multiprocessing.Queue,
#                                                  multiprocessing.Queue, ProcessSamples, PluginManager]:
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

        # Queues for UI
        data_queue = multiprocessing.Queue()
        control_queue = multiprocessing.Queue()

        display = WebServer.WebServer(data_queue, control_queue, logger.level, configuration.web_port)
        display.start()
        logger.debug(f"Started WebServer, {display}")

        # plugins, pass in all the variables as we don't know what the plugin may require
        plugin_manager = PluginManager.PluginManager(plugin_init_arguments=vars(configuration))

        data_source = create_source(configuration, factory)
        try:
            open_source(configuration, data_source)

            # attempt to connect, but allow exit if we receive a CTRL-C signal
            while not data_source.connected() and processing:
                try:
                    logger.debug(f"Input type {configuration.input_source} {configuration.input_params}")
                    data_source.connect()
                except Exception as err_msg:
                    logger.error(f"Connection problem {err_msg}")
                    time.sleep(1)

        except ValueError as msg:
            configuration.error = str(msg)

        # The main processor for producing ffts etc
        processor = ProcessSamples.ProcessSamples(configuration)

        return data_source, display, data_queue, control_queue, processor, plugin_manager, factory

    except Exception as msg:
        # exceptions here are fatal
        raise msg


def create_source(configuration: Variables, factory) -> DataSource:
    """
    Create the source of samples, cannot exception or fail. Does not open the source.

    :param configuration: All the config we need
    :param factory: Where we get the source from
    :return: The source
    """
    # TODO: Handle case when open fails and we have no source
    data_source = factory.create(configuration.input_source,
                                 configuration.input_params,
                                 configuration.fft_size,
                                 configuration.sample_type,
                                 configuration.sample_rate,
                                 configuration.centre_frequency_hz,
                                 configuration.source_sleep)
    return data_source


def open_source(configuration: Variables, data_source: DataSource) -> None:
    """
    Open the source, creating a source will not open it as the creation cannot fail but the open can

    :param configuration: Stores how the source is configured for our use
    :param data_source: The source we will open
    :return: None
    """
    data_source.open()

    # may have updated various things
    configuration.sample_type = data_source.get_sample_type()
    configuration.sample_rate = data_source.get_sample_rate()
    configuration.centre_frequency_hz = data_source.get_centre_frequency()

    # patch up fps things
    configuration.oneInN = int(configuration.sample_rate /
                               (configuration.fps * configuration.fft_size))

    # state and any errors or warning
    configuration.source_connected = data_source.connected()


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
        configuration.error = data_source.get_and_reset_error()
    except ValueError as msg:
        logger.error(f"Problem with new configuration, {msg} "
                     f"{configuration.centre_frequency_hz} "
                     f"{configuration.sample_rate} "
                     f"{configuration.fft_size}")
        configuration.error = str(msg)

    configuration.source_connected = data_source.connected()
    return data_source


def parse_command_line(configuration: Variables) -> None:
    """
    Parse all the command line options

    :param configuration: Where we store the configuration
    :return: None
    """
    # noinspection PyTypeChecker
    parser = argparse.ArgumentParser(epilog='',
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description=textwrap.dedent('''\
        Provide a spectral web UI of a stream of digitised complex samples.
        A variety of different input sources are supported.
        The web interface uses two ports, the web server and a websocket.
        The sample rate must be set for the programme to work correctly. When
        file input is used this sample rate may be recovered from the filename or
        from the meta data in a wav file.
        '''),
                                     )

    ######################
    # Input options
    ##########
    input_opts = parser.add_argument_group('Input')
    input_opts.add_argument('-W', '--wait', type=float, help="millisecond wait between reads for file "
                                                             f"input (default: {configuration.source_sleep})",
                            default=configuration.source_sleep, required=False)
    input_opts.add_argument('-i', '--input', type=str, help="Input, '?' for list", required=False)

    ######################
    # Sampling options
    ##########
    data_opts = parser.add_argument_group('Sampling')
    data_opts.add_argument('-c', '--centreFrequency', type=float,
                           help=f'Centre frequency in Hz (default: {configuration.centre_frequency_hz})',
                           default=configuration.centre_frequency_hz,
                           required=False)
    data_opts.add_argument('-s', '--sampleRate', type=float,
                           help=f'Sample rate in sps (default: {configuration.sample_rate})',
                           default=configuration.sample_rate,
                           required=False)
    data_opts.add_argument('-t', '--type',
                           help=f'Sample type (default: {configuration.sample_type})',
                           default=configuration.sample_type,
                           choices=DataSource.supported_data_types,
                           required=False)

    ######################
    # Misc options
    ##########
    misc_opts = parser.add_argument_group('Misc')
    misc_opts.add_argument('-F', '--fftSize', type=int, help=f'Size of FFT (default: {configuration.fft_size})',
                           default=configuration.fft_size, required=False)
    misc_opts.add_argument('-w', '--web', type=int, help=f'Web port, (default: default={configuration.web_port}), '
                                                         f'websocket one up from this)',
                           default=configuration.web_port, required=False)
    misc_opts.add_argument('-v', '--verbose', help='Verbose, -vvv debug, -vv info, -v warn', required=False,
                           action='count', default=0)
    misc_opts.add_argument('-H', '--HELP', help='This help', required=False, action='store_true')
    misc_opts.add_argument('-T', '--TIME', help='Time the spectral algorithm)', required=False, action='store_true')

    ######################
    # plugin options
    ##########
    plugin_opts = parser.add_argument_group('Plugin')
    plugin_opts.add_argument('--plugin', type=str,
                             help='Plugin options, ? to see help, e.g. analysis:peak:threshold:-10.',
                             required=False,
                             action='append', nargs='+')

    #####################
    # now parse them into configuration, suppose could of used a dictionary instead of a Class to hold these
    ############
    args = vars(parser.parse_args())

    if args['HELP'] is True:
        parser.print_help()
        list_sources()
        list_plugin_help()
        quit()

    if args['centreFrequency'] is not None:
        configuration.centre_frequency_hz = float(args['centreFrequency'])
    if args['sampleRate'] is not None:
        configuration.sample_rate = float(args['sampleRate'])
    if args['type'] is not None:
        configuration.sample_type = args['type']

    if args['wait']:
        configuration.source_sleep = float(args['wait']) / 1000.0
    if args['input'] is not None:
        full_source_name = args['input']
        if full_source_name == "?":
            list_sources()
            quit()  # EXIT now
        else:
            parts = full_source_name.split(":")
            if len(parts) >= 2:
                configuration.input_source = parts[0]
                # handle multiple ':' parts - make input_name up of them
                configuration.input_params = ""
                for part in parts[1:]:
                    # add ':' between values
                    if len(configuration.input_params) > 0:
                        configuration.input_params += ":"
                    configuration.input_params += f"{part}"
            else:
                logger.critical(f"input parameter incorrect, {full_source_name}")
                quit()

    if args['fftSize'] is not None:
        configuration.fft_size = abs(int(args['fftSize']))

    if args['web']:
        configuration.web_port = abs(int(args['web']))

    if args['verbose']:
        if args['verbose'] > 2:
            logger.setLevel(logging.DEBUG)
        elif args['verbose'] > 1:
            logger.setLevel(logging.INFO)
        elif args['verbose'] > 0:
            logger.setLevel(logging.WARNING)

    if args['plugin'] is not None:
        # is any of the options a '?'
        for plugin_opt in args['plugin']:
            if '?' in plugin_opt:
                list_plugin_help()
                quit()
        configuration.plugin_options = args['plugin']

    if args['TIME'] is True:
        time_spectral(configuration)
        quit()

    configuration.oneInN = int(configuration.sample_rate / (configuration.fps * configuration.fft_size))


def list_plugin_help() -> None:
    """
    Show the help for the plugins we discover
    :return: None
    """
    print("")
    plugin_manager = PluginManager.PluginManager(register=False)
    helps = plugin_manager.get_plugin_helps()
    print("Plugin helps:")
    for plugin, help_string in helps.items():
        print(f"{plugin}: {help_string}")
        print("")


def list_sources() -> None:
    """
    List the names of all the sources the current python environment can support

    :return: None
    """
    factory = DataSourceFactory.DataSourceFactory()
    print(f"Available sources: {factory.sources()}")
    helps = factory.help_strings()
    for input_name, help_string in helps.items():
        print(f"{help_string}")


def time_spectral(configuration: Variables):
    """
    Time how long it takes to compute various things and show results

    For FFT sizes Show results as max sps that would be possible all other things ignored
    :return: None
    """
    data_size = 2048
    # some random bytes, max of 4bytes per complex sample
    bytes_d = bytes([random.randrange(0, 256) for _ in range(0, data_size * 4)])
    print(f"data conversion time, 1Msps for 2048 samples is {data_size:0.1f}usec")
    print("data \tusec \tnsec/sample\ttype")
    print("===================================")
    for data_type in DataSource.supported_data_types:
        converter = DataSource.DataSource("null", data_size, data_type, 1e6, 1e6, 0)

        iterations = 1000
        time_start = time.perf_counter()
        for loop in range(iterations):
            _ = converter.unpack_data(bytes_d)
        time_end = time.perf_counter()

        processing_time = (time_end - time_start) / iterations
        processing_time_per_sample = processing_time / data_size
        print(f"{data_size} \t{processing_time * 1e6:0.1f} \t{processing_time_per_sample * 1e9:0.1f} \t\t{data_type}")

    # only measuring powers of two, not limited to that though
    fft_sizes = [256, 512, 1024, 2048, 4096, 8192, 16384, 32768]
    print("\nSpectral processing time (sps are absolute maximums for the basic spectral calculation)")
    print("spec \tusec  \tMsps")
    print("========================")
    for fft_size in fft_sizes:
        configuration.fft_size = fft_size
        processor = ProcessSamples.ProcessSamples(configuration)
        rands = np.random.rand(fft_size * 2)
        rands = rands - 0.5
        samples = np.array(rands[0::2], dtype=np.complex64)
        samples.imag = rands[1::2]

        iterations = 1000
        time_start = time.perf_counter()
        for loop in range(iterations):
            processor.process(samples)
        time_end = time.perf_counter()

        processing_time = (time_end - time_start) / iterations
        max_sps = fft_size / processing_time
        print(f"{fft_size} \t{processing_time * 1e6:0.1f} \t{max_sps / 1e6:0.3f}")
    print("")


def handle_control_queue(configuration: Variables,
                         ui_queue: multiprocessing.Queue,
                         control_queue: multiprocessing.Queue,
                         data_source,
                         source_factory):
    """
    Check the control queue for messages and handle them

    :param configuration: the current configuration
    :param ui_queue: The queue used for talking to the UI process
    :param control_queue: The queue to check on
    :param data_source:
    :param source_factory:
    :return:
    """
    try:
        config = control_queue.get(block=False)
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
                    configuration.oneInN = int(configuration.sample_rate /
                                               (configuration.fps * configuration.fft_size))
                elif new_config['type'] == "stop":
                    configuration.stop = int(new_config['value'])
                elif new_config['type'] == "sdrUpdate":
                    # TODO: copy the whole config instead
                    old_cf = configuration.centre_frequency_hz
                    old_sps = configuration.sample_rate
                    old_fft = configuration.fft_size
                    old_source = configuration.input_source
                    old_source_params = configuration.input_params
                    old_source_format = configuration.sample_type

                    if new_config['centreFrequencyHz'] != old_cf:
                        new_cf = new_config['centreFrequencyHz']
                        data_source.set_centre_frequency(new_cf)
                        configuration.centre_frequency_hz = data_source.get_centre_frequency()

                    if new_config['sps'] != old_sps:
                        new_sps = new_config['sps']
                        data_source.set_sample_rate(new_sps)
                        configuration.sample_rate = data_source.get_sample_rate()
                        configuration.oneInN = int(configuration.sample_rate /
                                                   (configuration.fps * configuration.fft_size))

                    if new_config['fftSize'] != old_fft:
                        configuration.fft_size = new_config['fftSize']
                        configuration.oneInN = int(configuration.sample_rate /
                                                   (configuration.fps * configuration.fft_size))
                        data_source.close()
                        data_source = update_source(configuration, source_factory)

                    if (new_config['source'] != old_source) \
                            or (new_config['sourceParams'] != old_source_params) \
                            or (new_config['dataFormat'] != old_source_format):
                        configuration.input_source = new_config['source']
                        configuration.input_params = new_config['sourceParams']
                        configuration.sample_type = new_config['dataFormat']
                        configuration.centre_frequency_hz = new_config['centreFrequencyHz']
                        logger.info(f"changing source to '{configuration.input_source}' "
                                    f"'{configuration.input_params}' '{configuration.sample_type}'")
                        data_source.close()
                        data_source = update_source(configuration, source_factory)

                # changes above may have produced errors in the data_source
                # configuration.error = data_source.get_and_reset_error()

                # reply with the current configuration whenever we receive something on the control queue
                ui_queue.put((configuration.make_json(), None, None, None, None, None))
                configuration.error = ""  # reset any error we are reporting

    except queue.Empty:
        pass

    return data_source


def update_ui(configuration: Variables,
              ui_queue: multiprocessing.Queue,
              powers: np.ndarray,
              peak_powers_since_last_display: np.ndarray,
              current_peak_count: int,
              max_peak_count: int,
              time_spectrum: float) -> Tuple[np.ndarray, int, int]:
    """
    Send data to the queue used for talking to the ui processes

    :param configuration: Our programme state variables
    :param ui_queue: The queue used for talking to the UI process
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

        if configuration.update_count >= configuration.oneInN:
            if ui_queue.qsize() < MAX_UI_QUEUE_DEPTH:
                configuration.update_count = 0
                # timings need to be altered
                if current_peak_count == 1:
                    configuration.time_first_spectrum = time_spectrum

                # order the spectral magnitudes, zero in the middle
                display_peaks = np.fft.fftshift(peak_powers_since_last_display)

                # data into the UI queue, we don't send state here
                state = None
                ui_queue.put((state, configuration.sample_rate, configuration.centre_frequency_hz,
                              display_peaks, configuration.time_first_spectrum, time_spectrum))

                # peak since last time is the current powers
                max_peak_count = current_peak_count
                current_peak_count = 0
                peak_powers_since_last_display = powers
                configuration.time_first_spectrum = time_spectrum
            else:
                peak_detect = True  # UI can't keep up
        else:
            peak_detect = True

        current_peak_count += 1  # count even when we throw them away

    if peak_detect:
        # Record the maximum for each bin, so that ui can show things between display updates
        peak_powers_since_last_display = np.maximum.reduce([powers, peak_powers_since_last_display])

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
                reconnect_count: int,
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
    :param reconnect_count: How many times we have reconnected to our data source
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
                 f'reconnects:{reconnect_count}, '
                 f'pc:{peak_count:0.1f}, '
                 f'fps:{fps}, '
                 f'mfps:{mfps}, '
                 f'1inN:{one_in_n} ')


if __name__ == '__main__':
    main()
