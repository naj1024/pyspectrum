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
from matplotlib_ui import DisplayProcessor
from dataProcessing import ProcessSamples
from misc import Ewma
from misc import PluginManager
from misc import Variables
from webUI import WebServer

processing = True  # global to be set to False from ctrl-c

# logging to our own logger, not the base one - we will not see log messages for imported modules
logger = logging.getLogger('spectrum_logger')
logging.basicConfig(format='%(levelname)s:%(name)s:%(module)s:%(message)s')
logger.setLevel(logging.WARNING)

# mmm TODO remove this global, just lazy
time_first_spectrum: float = 0


def signal_handler(sig, __):
    global processing
    processing = False
    print("Received signal", sig)


def main() -> None:
    if sys.version_info < (3, 7):
        logger.warning(f"Python version means sample timings will be course, python V{sys.version}")

    global processing
    signal.signal(signal.SIGINT, signal_handler)

    configuration = Variables.Variables()
    parse_command_line(configuration)

    # check we have a valid input sample type
    if configuration.sample_type not in configuration.sample_types:
        logger.critical(f'Illegal sample type of {configuration.sample_type} selected')
        quit()

    # configure us
    data_source, display, display_queue, control_queue, processor, plugin_manager, source_factory = initialise(
        configuration)

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
    reconnect_count = 0

    # keep processing until told to stop or an error occurs
    # loop_count = 0
    peak_average = Ewma.Ewma(0.1)
    current_peak_count = 0
    max_peak_count = 0
    while processing:

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

        # if there is a control message then it may change what the fron end is doing
        data_source = check_control_queue(configuration, control_queue, data_source, source_factory)

        ###########################################
        # Get the complex samples we will work on
        ######################
        try:
            data_samples_perf_time_start = time.perf_counter()
            samples, time_rx = data_source.read_cplx_samples()
            data_samples_perf_time_end = time.perf_counter()
            _ = sample_get_time.average(data_samples_perf_time_end - data_samples_perf_time_start)

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
                update_display(configuration,
                               display_queue,
                               processor.get_powers(
                                   False),
                               peak_powers_since_last_display,
                               current_peak_count,
                               max_peak_count,
                               time_rx)

            peak_average.average(
                max_peak_count)  # average of number of count of spectrums between matplotlib_ui updates

            complete_process_time_end = time.perf_counter()  # time for everything but data get
            process_time.average(complete_process_time_end - complete_process_time_start)

            # Debug print on how long things are taking
            if time.time() > debug_time:
                debug_time = debug_print(expected_samples_receive_time,
                                         configuration.fft_size, process_time,
                                         sample_get_time,
                                         reconnect_count,
                                         peak_average.get_ewma())

        except ValueError:
            # incorrect number of samples, probably because something closed
            if configuration.input_type == "file" and not configuration.source_loop:
                logger.info("End of input file")
                processing = False
            else:
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
        data_source.close()

    if display:
        if multiprocessing.active_children():
            # belt and braces
            display.kill()
            display.shutdown()
            display.join()

    if display_queue:
        # display_queue.close()
        while not display_queue.empty():
            _ = display_queue.get()

    print("exit")


# Problem defining what we return, DataSource can be many different things
# def initialise(configuration: Variables) -> Tuple[DataSource, DisplayProcessor, multiprocessing.Queue,
#                                                  multiprocessing.Queue, ProcessSamples, PluginManager]:
def initialise(configuration: Variables):
    try:
        # where we get our input samples from
        factory = DataSourceFactory.DataSourceFactory()
        # check that it is supported
        if configuration.input_type not in factory.sources():
            print("Available sources: ", factory.sources())
            raise ValueError(f"Error: Input source type of '{configuration.input_type}' is not supported")
        data_source = create_source(configuration, factory)

        # file input may need slowing down, but not all input types support sleep time
        try:
            data_source.set_sleep_time(configuration.source_sleep)
        except AttributeError:
            pass

        # attempt to connect, but allow exit if we receive a CTRL-C signal
        while not data_source.connected() and processing:
            try:
                logger.debug(f"Input type {configuration.input_type} {configuration.input_name}")
                data_source.connect()
            except Exception as err_msg:
                logger.error(f"Connection problem {err_msg}")
                time.sleep(1)

        # source may have modified sps or cf after connect
        read_source_config(configuration, data_source)

        # The main processor for producing ffts etc
        processor = ProcessSamples.ProcessSamples(configuration)

        # Queues for matplotlib_ui
        data_queue = multiprocessing.Queue()
        control_queue = multiprocessing.Queue()

        if configuration.web_display:
            display = WebServer.WebServer(data_queue, control_queue, logger.level, configuration.web_port)
            display.start()
        else:
            display = display_create(configuration, data_queue, control_queue, data_source.get_display_name())

        # plugins, pass in all the variables as we don't know what the plugin may require
        plugin_manager = PluginManager.PluginManager(plugin_init_arguments=vars(configuration))

        return data_source, display, data_queue, control_queue, processor, plugin_manager, factory

    except Exception as msg:
        # exceptions here are fatal
        raise msg


def create_source(configuration: Variables, factory):
    """
    Create the source of samples

    :param configuration: All the config we need
    :param factory: Where we get the source from
    :return: The source
    """
    data_source = factory.create(configuration.input_type,
                                 configuration.input_name,
                                 configuration.fft_size,
                                 configuration.sample_type,
                                 configuration.sample_rate,
                                 configuration.centre_frequency_hz)
    return data_source


def read_source_config(configuration: Variables, data_source):
    """
    Read back the values used by the source as they may have changed
    :param configuration: All the config we need
    :param data_source: The source we are using for samples
    :return: None
    """
    # read back these values as they may have changed from what we requested
    configuration.sample_rate = data_source.get_sample_rate()
    configuration.sample_type = data_source.get_sample_type()
    configuration.centre_frequency_hz = data_source.get_centre_frequency()


def parse_command_line(configuration: Variables) -> None:
    # noinspection PyTypeChecker
    parser = argparse.ArgumentParser(epilog='',
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description=textwrap.dedent('''\
        Provide a spectral matplotlib_ui of a stream of digitised complex samples.
        
        A variety of different input sources are supported
        
        We expect to process all samples at the digitisation rate. The digitised samples 
        can be from a file, socket, Pluto or rtl device.
        
        The sample rate must be set for the programme to work correctly. When
        file input is used this sample rate may be recovered from the filename or
        from the meta data in a wav file.
        
          The matplotlib_ui has mouse actions::
           Spectrum:    left   - Print frequency and power to stdout.
                               - Toggle trace visibility if mouse is near a legend line.
                        middle - Toggle visibilty of the frequency annotations.
                        right  - Turn on/off/reset the peak hold trace.
                        scroll - dB range, top of spectrum for max limit, bottom for min limit
           Spectrogram: left   - Print frequency and power to stdout.
                        middle - Reset dB shift
                        right  - Pause spectrogram.
                        scroll - shift dB range up or down 
           Elsewhere:   Any    - Toggle visibilty of legend in Spectrum matplotlib_ui. 
        '''),
                                     )

    ######################
    # Input options
    ##########
    input_opts = parser.add_argument_group('Input')
    input_opts.add_argument('-L', '--loop', help="Loop file input", required=False, action='store_true', default=False)
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
                           choices=configuration.sample_types,
                           required=False)

    ######################
    # Misc options
    ##########
    misc_opts = parser.add_argument_group('Misc')
    misc_opts.add_argument('-F', '--fftSize', type=int, help=f'Size of FFT (default: {configuration.fft_size})',
                           default=configuration.fft_size, required=False)
    misc_opts.add_argument('-E', '--spectrogram',
                           help=f'Add a spectrogram on matplotlib_ui',
                           default=False, required=False, action='store_true')
    misc_opts.add_argument('-w', '--web', type=int, help=f'Web interface port plus websocket one up from this', required=False)
    misc_opts.add_argument('-v', '--verbose', help='Verbose, -vvv debug, -vv info, -v warn', required=False,
                           action='count', default=0)
    misc_opts.add_argument('-H', '--HELP', help='Full help (even within gooey)', required=False, action='store_true')
    misc_opts.add_argument('-T', '--TIME', help='Time the spectral algorithm)', required=False, action='store_true')

    # The following option is here for when gooey is not installed in the python environment and we still
    # pass in the gooey option to not use the commandlineUI, which means we get the option and have to ignore it
    misc_opts.add_argument('--ignore-gooey', help='Ignore Gooey commandlineUI if it is present',
                           required=False, action='store_true')

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

    if args['loop']:
        configuration.source_loop = args['loop']
    if args['wait']:
        configuration.source_sleep = float(args['wait']) / 1000.0
    if args['input'] is not None:
        full_source_name = args['input']
        if full_source_name == "?":
            list_sources()
            quit()  # EXIT now
        else:
            parts = full_source_name.split(":")
            if len(parts) == 2:
                configuration.input_type = parts[0]
                configuration.input_name = parts[1]
            else:
                logger.critical(f"input parameter incorrect, {full_source_name}")
                quit()

    if args['fftSize'] is not None:
        configuration.fft_size = abs(int(args['fftSize']))

    if args['spectrogram']:
        configuration.spectrogram_flag = args['spectrogram']

    if args['web']:
        configuration.web_display = True;
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
    print("")
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
        converter = DataSource.DataSource("null", data_size, data_type, 1e6, 1e6)

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

def check_control_queue(configuration: Variables,
                        control_queue: multiprocessing.Queue,
                        data_source,
                        source_factory):
    """
    Check the control queue for messages and handle them

    :param configuration: the current configuration
    :param control_queue: The queue to check on
    :param data_source:
    :param source_factory:
    :return:
    """
    try:
        config = control_queue.get(block=False)
        if config:
            # config message is a json string
            # e.g. {"name":"unknown","centreFrequencyHz":433799987,"sps":600000,
            #       "bw":600000,"fftSize":"8192","sdrStateUpdated":false}
            try:
                new_config = json.loads(config)
                reconfigure = False
                old_cf = configuration.centre_frequency_hz;
                old_sps = configuration.sample_rate;
                old_fft = configuration.fft_size;

                if new_config['centreFrequencyHz'] != old_cf:
                    configuration.centre_frequency_hz = new_config['centreFrequencyHz']
                    reconfigure = True
                if new_config['sps'] != old_sps:
                    configuration.sample_rate = new_config['sps']
                    reconfigure = True
                if new_config['fftSize'] != old_fft:
                    configuration.fft_size = new_config['fftSize']
                    reconfigure = True

                if reconfigure:
                    data_source.close()
                    try:
                        data_source = create_source(configuration, source_factory)
                    except ValueError as msg:
                        logger.error(f"Problem with new configuration, {msg} "
                                     f"{configuration.centre_frequency_hz} "
                                     f"{configuration.sample_rate} "
                                     f"{configuration.fft_size}")
                        # put things back
                        configuration.centre_frequency_hz = old_cf
                        configuration.sample_rate = old_sps
                        # bodge just to get config table updated
                        configuration.fft_size = old_fft // 2  # TODO handle errors back to UI
                        data_source = create_source(configuration, source_factory)

            except ValueError as msg:
                logger.error(f"Problem with json control message {config}, {msg}")
                pass

    except queue.Empty:
        pass

    return data_source

def update_display(configuration: Variables,
                   display_queue: multiprocessing.Queue,
                   powers: np.ndarray,
                   peak_powers_since_last_display: np.ndarray,
                   current_peak_count: int,
                   max_peak_count: int,
                   time_spectrum: float) -> Tuple[np.ndarray, int, int]:
    """
    Send data to the queue used for talking to the ui processes

    :param configuration: Our programme state variables
    :param display_queue: The queue used for talking to the matplotlib_ui process
    :param powers: The powers of the spectrum bins
    :param peak_powers_since_last_display: The powers since we last updated the matplotlib_ui
    :param current_peak_count: count of spectrums we have peak held on
    :param max_peak_count: maximum since last time it was reset
    :param time_spectrum: Time of this spectrum in nano seconds
    :return: array of updated peak powers
    """
    # guess this should be a class as i'm using a global for a static
    global time_first_spectrum

    if display_queue.qsize() < DisplayProcessor.MAX_DISPLAY_QUEUE_DEPTH:
        # if we are keeping up then timings need to be altered
        if current_peak_count == 1:
            time_first_spectrum = time_spectrum
        # Send the things to be displayed off to the matplotlib_ui process
        display_powers = np.fft.fftshift(powers)
        display_peaks = np.fft.fftshift(peak_powers_since_last_display)
        display_queue.put((True, configuration.sample_rate, configuration.centre_frequency_hz,
                           display_powers, display_peaks, time_first_spectrum, time_spectrum))

        # peak since last time is the current powers
        max_peak_count = current_peak_count
        current_peak_count = 0
        peak_powers_since_last_display = powers
        time_first_spectrum = time_spectrum
    else:
        # Record the maximum for each bin, so that ui can show things between matplotlib_ui updates
        peak_powers_since_last_display = np.maximum.reduce([powers, peak_powers_since_last_display])

    current_peak_count += 1  # count even when we throw them away

    if not multiprocessing.active_children():
        configuration.display_on = False
        print("Spectrum window closed")
        global processing
        processing = False  # we will exit mow

    return peak_powers_since_last_display, current_peak_count, max_peak_count


def display_create(configuration: Variables,
                   display_queue: multiprocessing.Queue,
                   control_queue: multiprocessing.Queue,
                   input_name: str) -> DisplayProcessor:
    """
    Create the matplotlib_ui process (NOT a thread)

    :param configuration: Our state
    :param display_queue: The queue we will use for talking to the created matplotlib_ui process
    :param control_queue: The queue we will use for the matplotlib_ui to send back control
    :param input_name: What the input is called
    :return: The handle to the matplotlib_ui process
    """
    window_title = f"{configuration.input_type} {input_name}"
    display = DisplayProcessor.DisplayProcessor(window_title,
                                                display_queue,
                                                control_queue,
                                                configuration.fft_size,
                                                configuration.sample_rate,
                                                configuration.centre_frequency_hz,
                                                configuration.spectrogram_flag)
    display.start()
    return display


def debug_print(expect_samples_receive_time: float,
                fft_size: int,
                process_time: Ewma,
                sample_get_time: Ewma,
                reconnect_count: int,
                peak_count: float) -> float:
    """
    Various useful profiling prints

    :param expect_samples_receive_time: How long the samples would of taken to digitise
    :param fft_size: The number of samples per cycle
    :param process_time: How long we have spent processing the samples
    :param sample_get_time: How long it took as to receive the digitised samples
    :param reconnect_count: How many times we have reconnected to our data source
    :param peak_count: Count of how many spectrums we are peak detecting on for the matplotlib_ui
    :return: New last debug update time
    """
    # approx fps
    fps = -1
    total_time = sample_get_time.get_ewma() + process_time.get_ewma()
    if peak_count > 0:
        if total_time > 0:
            fps = 1 / (total_time * peak_count)
    else:
        # running real time
        fps = 1 / expect_samples_receive_time

    logger.debug(f'FFT:{fft_size} '
                 f'{1e6 * expect_samples_receive_time:.0f}usec, '
                 f'read:{1e6 * sample_get_time.get_ewma():.0f}usec, '
                 f'process:{1e6 * process_time.get_ewma():.0f}usec, '
                 f'total:{1e6 * total_time:.0f}usec, '
                 f'connects:{reconnect_count}, '
                 f'pc:{peak_count:0.1f}, '
                 f'fps:{fps:0.0f}')

    debug_time = time.time() + 5
    return debug_time


if __name__ == '__main__':
    main()
