import numpy as np
from typing import List
import logging
# import line_profiler

from dataProcessing import Spectrum
from misc import Variables

logger = logging.getLogger('spectrum_logger')


def convert_to_frequencies(bins: List[int], sample_rate: float, fft_size: int) -> List[float]:
    """

    :param bins: sparse list of bins from an fft (with fftshift already applied)
    :param sample_rate: The sample rate used
    :param fft_size: The size of the fft
    :return: A list of frequencies defined by the sparse bin list
    """
    return Spectrum.convert_to_frequencies(bins, sample_rate, fft_size)


def get_windows() -> []:
    return Spectrum.get_windows()


class ProcessSamples:

    def __init__(self, configuration: Variables):
        """
        The main processor for digitised samples
        :param configuration: The configuration we want
        """
        self._spec = Spectrum.Spectrum(configuration.fft_size, configuration.window)

        self._long_average = np.zeros(configuration.fft_size)
        self._powers = np.zeros(configuration.fft_size)
        self._alpha_for_ewma = 0.01

        # easier to ignore divide by zeros than test for them
        np.seterr(divide='ignore')

    # @profile
    def process(self, samples: np.ndarray) -> None:
        """Process digitised samples to detect signals in the frequency domain

        :param samples: An numpy array of complex samples - which is ALWAYS the FFT size
        :return: None
        """
        magnitudes_squared = self._spec.mag_spectrum(samples, False)
        self._powers = Spectrum.get_powers(magnitudes_squared)

        # check that the size of the arrays have not changed, i.e. FFT size changed
        if samples.size != self._long_average.size:
            self._long_average = np.zeros(samples.size)
            self._powers = np.zeros(samples.size)

        # Update a noise riding average
        # long term average on each bin to give a per bin noise floor
        # new = alpha * new_sample + (1-alpha) * old
        self._long_average *= (1 - self._alpha_for_ewma)
        self._long_average += (self._powers * self._alpha_for_ewma)

    def get_long_average(self, reorder: bool = False) -> np.ndarray:
        """
        Return the long term average of the the fft powers

        :param reorder: Reorder the returned result with fftshift
        :return: The fft bin averages in dB
        """
        if reorder:
            return np.fft.fftshift(self._long_average)
        return self._long_average

    def get_powers(self, reorder: bool = False) -> np.ndarray:
        """The FFT bin powers

        :param reorder: True if fftshift is used to give the array with -ve to +ve freq and zero in the middle
        :return: The fft bin powers in dB
        """
        if reorder:
            return np.fft.fftshift(self._powers)
        return self._powers

    def set_window(self, window:str) -> None:
        self._spec.set_window(window)

    def get_window(self) -> str:
        return self._spec.get_window()