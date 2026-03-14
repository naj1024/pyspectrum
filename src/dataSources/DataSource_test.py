"""
Test class for magnitude source
"""

import logging
import math
from typing import Tuple
import time

import numpy as np

from dataSources import DataSource
from dataProcessing import Spectrum

logger = logging.getLogger('spectrum_logger')

module_type = "test"
help_string = f"{module_type}:snr_dB"
web_help_string = "A test source with a ramping signal snr_db above noise"
import_error_msg = ""

# return an error string if we are not available
def is_available() -> Tuple[str, str]:
    return module_type, import_error_msg


# noinspection PyUnusedLocal
class Input(DataSource.DataSource):

    def __init__(self,
                 parameters: str,
                 data_type: str,
                 sample_rate: float,
                 centre_frequency: float,
                 input_bw: float):
        """
        Test source

        :param parameters: The address the device should be on
        :param data_type: Not used
        :param sample_rate: The sample rate the pluto device will be set to, AND it's BW
        :param centre_frequency: The Centre frequency we will tune to
        :param input_bw: The filtering of the input, may not be configurable
        """

        # Driver converts to floating point for us, underlying data from ad936x was 16bit i/q
        self._constant_data_type = "16tle"

        self._min_frequency = 0.0
        self._max_frequency = 6000000000.0

        super().__init__(parameters, self._constant_data_type, sample_rate, centre_frequency, input_bw)
        self._name = module_type
        self._connected = False
        self._gain_modes = ["manual"]
        super().set_gain_mode(self._gain_modes[0])
        super().set_help(help_string)
        super().set_web_help(web_help_string)

        try:
            self._snr_db = float(self._parameters)
        except Exception as k:
            self._snr_db = 200.0  # very high snr
        logger.info(f"Test source using snr of {self._snr_db}dB")

        self._last_time = time.time_ns()
        self._doing_mags = False
        self._max_amp = 0.001    # dont really want +-1.0 for the samples

        logger.info(f"New test source with FIXED Hanning window, {self._sample_rate_sps}sps, {self._gain}, {self._snr_db}dB")
        self._spec = Spectrum.Spectrum(512, 'Hanning')

    def open(self) -> bool:
        global import_error_msg
        if import_error_msg != "":
            msgs = f"no {module_type} device available, {import_error_msg}"
            self._error = msgs
            logger.error(msgs)
            raise ValueError(msgs)

        if self._parameters == "?":
            self._error = f"Can't scan for {module_type} devices"
            return False

        logger.debug(f"Connected to {module_type} on {self._parameters}")
        self._connected = True
        return self._connected

    def set_sample_type(self, data_type: str) -> None:
        # we can't set a different sample type on this source
        super().set_sample_type(self._constant_data_type)

    def read_cplx_samples(self, number_samples: int) -> Tuple[np.array, float]:
        Fs = self._sample_rate_sps
        N = number_samples

        # Initialise state
        if not hasattr(self, "_current_freq"):
            self._current_freq = -Fs / 2.0
        if not hasattr(self, "_osc_phase"):
            self._osc_phase = 1 + 0j   # complex phase accumulator

        # Phase step for this frequency
        phase_step = np.exp(1j * 2 * np.pi * self._current_freq / Fs)

        # Generate oscillator samples
        signal = np.empty(number_samples, dtype=np.complex64)

        p = self._osc_phase
        for i in range(number_samples):
            signal[i] = p
            p *= phase_step

        # Frequency step per call
        self._current_freq += Fs / 8192

        # Wrap to [-Fs/2, Fs/2)
        if self._current_freq >= Fs / 2:
            self._current_freq -= Fs

        # Signal power
        sig_power = np.mean(np.abs(signal) ** 2)

        # Desired noise level
        snr_linear = 10 ** ((self._snr_db -23) / 10)  # not sure why i'm out by 23dB probably tied up with sample/fft size
        noise_power = sig_power / snr_linear
        noise_std_per_component = np.sqrt(noise_power / 2)  # split between I and Q

        # Add Gaussian noise
        noise1 = np.random.normal(0, noise_std_per_component, N)
        noise2 = np.random.normal(0, noise_std_per_component, N)
        signal_noisy = signal + (noise1 + 1j * noise2)

        # add gain
        signal_noisy *= self._max_amp
        signal_noisy *= 10 ** (self._gain / 20.0)

        rx_time = 0
        if not self._doing_mags:
            rx_time = self.simulate_sample_wait_time(number_samples, rx_time)

        # always clear this flag
        self._doing_mags = False

        return signal_noisy, rx_time

    def read_magnitude_samples(self, number_samples: int) -> Tuple[np.ndarray, float]:
        self._doing_mags = True
        rx_time = time.time_ns()

        signal, rx_time = self.read_cplx_samples(number_samples)
        magnitudes_squared = self._spec.mag_spectrum(signal, False)

        rx_time = self.simulate_sample_wait_time(number_samples, rx_time)

        return magnitudes_squared, rx_time

    def simulate_sample_wait_time(self, number_samples: int, rx_time: int) -> float:
        elapsed = (time.time_ns() - self._last_time) * 1e-9
        wait = (number_samples / self._sample_rate_sps) - elapsed
        if wait > 0:
            time.sleep(wait)
        rx_time = time.time_ns()
        self._last_time = rx_time * 0.8  # don't take all the time
        return rx_time
