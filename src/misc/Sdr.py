"""
Class to hold all the programmes variables that we need to pass around

Used because we seem to need a lot of these in different places during initialisation

Passed to the UI as a jason string every few seconds
"""
import asyncio
from dataclasses import dataclass

@dataclass
class Sdr:
    sample_rate = 1e6  # default
    effective_sample_rate = sample_rate # we will calculate what we are getting
    centre_frequency_hz = 433.92e6  # used by the sdr
    conversion_frequency_hz = 0.0
    sdr_centre_frequency_hz = centre_frequency_hz - conversion_frequency_hz
    sample_types = ['8o', '8t', '16tbe', '16tle', '32fle', '32fbe']
    sample_type = '16tbe'  # default Format of sample data
    total_samples = 0
    time_last_effective_calc = 0
    gain = 0
    gain_modes = ['none']
    gain_mode = "none"
    input_bw_hz = sample_rate
    ppm_error = 0.0
    dbm_offset = 0.0
    dc_removal = "Off"
    dc_error = complex(0, 0)
    input_level = 0.0
    seconds_current = 0.0
    seconds_length = 0.0

    # input data related
    fft_size = 2048  # default, but any integer allowed
    psd = False
    fft_rbw = 0
    fft_overlaps = [0, 25, 50, 75]  # 25 and 75 seem to give problems with reading sources - not quick enough?
    fft_overlap = 0
    fft_frame_time = 1e6 * (fft_size / sample_rate)  # useconds
    window = ""
    window_types = []
    read_magnitudes = False  # for sources that will give fft magnitudes instead of samples

    loop_cpu_pc = 0.0  # % of fft/sample rate time being used
    max_cpu_core_pc = 0.0

    # display
    fps = 20
    dog = asyncio.Event()  # for sending data at fps, guard when things go wrong
    update_count = 0
    measured_fps = 20
    time_measure_fps = 0
    sent_count = 0
    stop = False
    web_port = 8080

    peak_detect = True # we can turn off peak detection between spectrums output at fps
    fps_send_flag = True  # when set to false the sending of data to the ui is disabled

    # for interface to UI
    ackTime = 0  # time in seconds of the last data displayed by the UI, updated by UI
    ui_delay = 0  # measured difference between now and ack from ui
    expected_one_in_n = max(int(sample_rate / (fps * fft_size)), 1)
    actual_one_in_n = expected_one_in_n

    # where the data comes from
    input_source = "null"  # the source type e.g. file, socket, pluto, soapy, rtlsdr, audio ....
    input_params = ""  # the parameters for the source, e.g. filename or ip address ...
    time_first_spectrum: float = 0
    source_connected = False
    input_overflows = 0

    # List of data source, discovered by looking in dataSources directory
    input_sources = []
    input_sources_with_helps = []

    # List of plugin options, discovered by looking in plugins directory
    #   --plugin xyz:abc:def
    plugin_options = []

    error = ""  # any errors we want to have available in the UI


def add_to_error(config: Sdr, err: str) -> None:
    if len(err) != 0:
        config.error += f"{err}\n"


def get_and_reset_error(config: Sdr) -> str:
    tmp = config.error
    config.error = ""
    return tmp
