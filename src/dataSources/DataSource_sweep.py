"""
Test class for a sample and magnitude source

Note: Can't change the fft window.
"""

import logging
import math
from typing import Tuple
import time

import numpy as np
import numpy.typing as npt

from dataSources import DataSource
from dataProcessing import Spectrum

logger = logging.getLogger('spectrum_logger')

module_type = "sweep"
help_string = f"{module_type}:snr_dB"
web_help_string = "A test source with a sweeping signal at snr_db above noise"
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
        Sweep test source

        :param parameters: snr of the sweeping tone
        :param data_type: Not used
        :param sample_rate: The sample rate the pluto device will be set to, AND it's BW
        :param centre_frequency: The Centre frequency we will tune to
        :param input_bw: The filtering of the input, may not be configurable
        """

        self._constant_data_type = "32fle"
        if not parameters or parameters == "":
            parameters = "40"  # default of 40dB snr

        super().__init__(parameters, self._constant_data_type, sample_rate, centre_frequency, input_bw)

        self._min_frequency = 0.0
        self._max_frequency = 6000000000.0
        self._name = module_type
        self._connected = False
        self._gain_modes = ["manual"]
        super().set_gain_mode(self._gain_modes[0])
        super().set_help(help_string)
        super().set_web_help(web_help_string)

        self._offset = 10  # To make peak signal above noise correct
        try:
            self._snr_db = float(self._parameters) + self._offset
        except ValueError:
            self._snr_db = 200.0  # very high snr
            logger.error(f"Test data source defaulting snr as '{self._parameters}' not a number")
        logger.info(f"Test source using snr of {self._snr_db}dB")

        self._max_amp = 0.0001    # dont really want +-1.0 for the samples

        self._current_freq = -sample_rate / 8.0  # starts 1/8 of way from negative extreme
        self._osc_phase = np.complex64(1 + 0j)

        self.enbw = 0
        self.enbw_db = 0
        self.change_spectrum(512, 'Hanning')

    def set_spectral_output(self, active: bool):
        # configure source to output spectrums
        self._spectral_output = active

    def change_spectrum(self, n: int, window: str) -> None:
        self._spec = Spectrum.Spectrum(n, window)
        self._enbw_db= 10 * math.log10(self._spec.get_enbw())
        self._enbw = 10 * math.log10(self._spec.get_enbw())

        logger.info(f"Test source with magnitudes {n}, "
                    f"{self._spec.get_window()}, "
                    f"{self._sample_rate_sps}sps, "
                    f"enbw {self._spec.get_enbw():.3f}, "
                    f"rbw {self._spec.get_rbw(self._sample_rate_sps):.1f}Hz")


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

    def read_cplx_samples(self, number_samples: int) -> Tuple[npt.NDArray[np.complex64], float]:

        time_in = time.time_ns()

        Fs = self._sample_rate_sps
        N = number_samples

        # Phase step for this frequency
        phase_step = np.complex64(np.exp(1j * 2 * np.pi * self._current_freq / Fs))

        # generate samples
        phases = np.arange(number_samples, dtype=np.float64)
        signal = (self._osc_phase * np.exp(1j * 2 * np.pi * self._current_freq / Fs * phases)).astype(np.complex64)

        # advance for next call
        self._osc_phase = signal[-1] * phase_step

        # Frequency step per call and wrap to [-Fs/2, Fs/2)
        self._current_freq += Fs / 8192  # decent sweep rate
        if self._current_freq >= Fs / 2:
            self._current_freq -= Fs

        # Desired noise level
        fft_gain_db = 10 * math.log10(N)
        snr_offset_db = fft_gain_db - self._enbw_db
        snr_linear = 10 ** ((self._snr_db - snr_offset_db) / 10)

        sig_power = 1.0  # complex exponential has unity power
        noise_power = sig_power / snr_linear
        noise_std_per_component = np.sqrt(noise_power / 2)

        # Add Gaussian noise, make sure we stay as complex64
        noise = (
                np.random.normal(0, noise_std_per_component, N).astype(np.float32)
                + 1j * np.random.normal(0, noise_std_per_component, N).astype(np.float32)
        )
        signal_noisy = signal + noise.astype(np.complex64)

        # limit max as we don't want full scale test signals
        signal_noisy *= np.float32(self._max_amp)

        # add gain
        signal_noisy *= 10 ** (self._gain / 20.0)

        # always set the time
        rx_time = self.simulate_sample_wait_time(number_samples)

        return signal_noisy, rx_time

    def read_magnitude_samples(self, number_samples: int) -> Tuple[np.ndarray, float]:

        # do we need to update the spectrum, update enbw_db
        if number_samples != self._spec.get_fft_size():
            self.change_spectrum(number_samples, self._spec.get_window())

        signal, rx_time = self.read_cplx_samples(number_samples)
        magnitudes_squared = self._spec.mag_spectrum(signal, False)

        return magnitudes_squared, rx_time

