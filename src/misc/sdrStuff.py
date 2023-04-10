import logging

from dataSources import DataSource
from misc import Sdr

logger = logging.getLogger('spectrum_logger')


def change_source(data_source, source_factory, configuration: Sdr, source, params):
    if source != "":
        configuration.input_source = source
        configuration.input_params = params
        logger.info(f"changing source to '{configuration.input_source}' "
                    f"'{configuration.input_params}'")
        data_source.close()
        Sdr.add_to_error(configuration, data_source.get_and_reset_error())
        data_source = update_source(configuration, source_factory)
    else:
        logger.error("Attempt to use empty source parameter")

    return data_source


def create_source(configuration: Sdr, factory) -> DataSource:
    """
    Create the source of samples, cannot exception or fail. Does not open the source.

    :param configuration: All the config we need
    :param factory: Where we get the source from
    :return: The source, has still to be opened
    """
    data_source = factory.create(configuration.input_source,
                                 configuration.input_params,
                                 configuration.sample_type,
                                 configuration.sample_rate,
                                 configuration.centre_frequency_hz - configuration.conversion_frequency_hz,
                                 configuration.input_bw_hz)
    return data_source


def open_source(config: Sdr, data_source: DataSource) -> None:
    """
    Open the source, just creating a source will not open it as the creation cannot fail but the open can

    :param config: Stores how the source is configured for our use
    :param data_source: The source we will open
    :return: None
    """
    # few other things to configure first before the open()
    data_source.set_gain_mode(config.gain_mode)
    data_source.set_gain(config.gain)

    if data_source.open():
        # may have updated various things
        config.sample_type = data_source.get_sample_type()
        config.sample_rate = data_source.get_sample_rate_sps()
        config.sdr_centre_frequency_hz = data_source.get_centre_frequency_hz()
        config.centre_frequency_hz = config.sdr_centre_frequency_hz + config.conversion_frequency_hz
        config.gain = data_source.get_gain()
        config.gain_modes = data_source.get_gain_modes()
        config.gain_mode = data_source.get_gain_mode()
        config.input_bw_hz = data_source.get_bandwidth_hz()
        ppm = data_source.get_ppm()
        if ppm == 0.0:
            data_source.set_ppm(config.ppm_error)
        else:
            config.ppm_error = ppm

            # state any errors or warning
        config.source_connected = data_source.connected()

    Sdr.add_to_error(config, data_source.get_and_reset_error())


def update_source_state(configuration: Sdr, data_source: DataSource) -> None:
    """
    Things that the source may change on it's own that we need to be aware of for the UI etc

    :param configuration: How we think we are configured
    :param data_source:  Which source to check
    :return: None
    """
    if data_source:
        configuration.gain = data_source.get_gain()  # front end may have an auto mode
        configuration.sample_rate = data_source.get_sample_rate_sps()  # sps may have some resolution
        configuration.sdr_centre_frequency_hz = data_source.get_centre_frequency_hz()  # front end resolution


def update_source(configuration: Sdr, source_factory) -> DataSource:
    """
    Changing the source

    :param configuration: For returning how source is configured
    :param source_factory: How we will generate a new source
    :return: The DataSource
    """
    data_source = create_source(configuration, source_factory)
    try:
        # we may just be updating the source (maybe fft size related), so reset the gain to what we expect
        gain_mode = configuration.gain_mode
        gain = configuration.gain
        open_source(configuration, data_source)
        Sdr.add_to_error(configuration, data_source.get_and_reset_error())
        data_source.set_gain_mode(gain_mode)
        data_source.set_gain(gain)
        logger.info(f"Opened source {configuration.input_source}")
    except ValueError as msg:
        logger.error(f"Problem with new configuration, {msg} "
                     f"{configuration.centre_frequency_hz} "
                     f"{configuration.sample_rate} "
                     f"{configuration.fft_size}")
        Sdr.add_to_error(configuration, str(msg))
        configuration.input_source = "null"
        data_source = create_source(configuration, source_factory)
        open_source(configuration, data_source)

    configuration.source_connected = data_source.connected()
    return data_source
