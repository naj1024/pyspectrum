import logging
from typing import Dict

from dataProcessing import ProcessSamples
from dataSources import DataSource
from misc import sdrVariables

logger = logging.getLogger('spectrum_logger')


def handle_sdr_message(configuration: sdrVariables, new_config: Dict, data_source,
                       source_factory, processor: ProcessSamples) -> DataSource:
    """
    Handle specific sdr related control messages
    :param configuration: current config
    :param new_config: dictionary from a json string with possible new config
    :param data_source: where we get data from currently
    :param source_factory:
    :param processor:
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

        if new_config['window'] != configuration.window:
            new_window = new_config['window']
            processor.set_window(new_window)
            configuration.window = processor.get_window()

        if new_config['sps'] != configuration.sample_rate:
            new_sps = new_config['sps']
            data_source.set_sample_rate_sps(new_sps)
            configuration.error += data_source.get_and_reset_error()
            configuration.sample_rate = data_source.get_sample_rate_sps()

        if new_config['fftSize'] != configuration.fft_size:
            configuration.fft_size = new_config['fftSize']
            data_source.close()  # can't change the block size without opening again
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


def create_source(configuration: sdrVariables, factory) -> DataSource:
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


def open_source(configuration: sdrVariables, data_source: DataSource) -> None:
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

        # state any errors or warning
        configuration.source_connected = data_source.connected()

    configuration.error += data_source.get_and_reset_error()


def update_source_state(configuration: sdrVariables, data_source: DataSource) -> None:
    """
    Things that the source may change on it's own that we need to be aware of for the UI etc

    :param configuration: How we think we are configured
    :param data_source:  Which source to check
    :return: None
    """
    if data_source:
        configuration.gain = data_source.get_gain()  # front end may have an auto mode
        configuration.sample_rate = data_source.get_sample_rate_sps()  # sps may have some resolution
        configuration.centre_frequency_hz = data_source.get_centre_frequency_hz()  # front end may have some resolution


def update_source(configuration: sdrVariables, source_factory) -> DataSource:
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
