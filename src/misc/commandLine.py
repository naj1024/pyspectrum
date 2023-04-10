import argparse
import logging
import os
import textwrap

from dataSources import DataSource
from dataSources import DataSourceFactory
from misc import PluginManager
from misc import Sdr
from misc import timeSpectral


def parse_command_line(configuration: Sdr, logger: logging.Logger) -> None:
    """
    Parse all the command line options

    :param configuration: Where we store the configuration
    :param logger: logging
    :return: None
    """
    # noinspection PyTypeChecker
    parser = argparse.ArgumentParser(epilog='',
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description=textwrap.dedent('''\
        Provide a spectral web UI for a stream of digitised complex samples.
        A web interface is provided and uses requires two ports.
        
        Try:
            python3 ./SpectrumAnalyser.py -i? 
                Add -vvv for more debug
        
            Web
            python3 ./SpectrumAnalyser.py 
            
        Best to configure through the web interface, default is on port 8080.
        Select a source and type and give '?' as the option to see available sources
        
        Check log files under src/logs
        '''),
                                     )

    ######################
    # Input options
    ##########
    input_opts = parser.add_argument_group('Input')
    input_opts.add_argument('-i', '--input', type=str, help="Input, '?' for list", required=False)

    ######################
    # Sampling options
    ##########
    data_opts = parser.add_argument_group('Sampling')
    data_opts.add_argument('-c', '--centreFrequency', type=float,
                           help=f'Centre frequency in Hz (default: {configuration.centre_frequency_hz})',
                           default=configuration.centre_frequency_hz,
                           required=False)
    data_opts.add_argument('-C', '--conversionFrequency', type=float,
                           help=f'Up/down conversion frequency in Hz '
                                f'(default: {configuration.conversion_frequency_hz})',
                           default=configuration.conversion_frequency_hz,
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
    if args['conversionFrequency'] is not None:
        configuration.conversion_frequency_hz = float(args['conversionFrequency'])
    if args['sampleRate'] is not None:
        configuration.sample_rate = float(args['sampleRate'])
    if args['type'] is not None:
        configuration.sample_type = args['type']

    # allow for conversion frequency
    configuration.sdr_centre_frequency_hz = configuration.centre_frequency_hz - configuration.conversion_frequency_hz

    if args['input'] is not None:
        full_source_name = args['input']
        if full_source_name == "?":
            list_sources()
            quit()  # EXIT now
        else:
            parts = full_source_name.split(":")
            if len(parts) >= 1:
                configuration.input_source = parts[0]
                # handle multiple ':' parts - make input_name up of them
                configuration.input_params = ""
                if len(parts) >= 2:
                    for part in parts[1:]:
                        # add ':' between values
                        if len(configuration.input_params) > 0:
                            configuration.input_params += ":"
                        configuration.input_params += f"{part}"
                if configuration.input_source == 'file':
                    configuration.input_params = os.path.basename(configuration.input_params)
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
        timeSpectral.time_spectral(configuration)
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
