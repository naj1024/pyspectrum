import time
import os
from typing import List
import logging
# import line_profiler

import numpy as np

logger = logging.getLogger('spectrum_logger')

try:
    import scipy
    from scipy import fftpack
except ImportError:
    fftpack = None
    logger.info("No scipy support in environment")

try:
    import pyfftw  # seems best suited for large FFT sizes, >8192

    pyfftw.interfaces.cache.enable()  # planner cache
    pyfftw.interfaces.cache.set_keepalive_time(5)  # keep fftw things cache alive for 5 seconds between calls
except ImportError:
    pyfftw = None
    logger.info("Warning: No fftw support in environment")


def create_test_data(size: int) -> np.array:
    # create some test data
    rnd = np.random.rand(size * 2)
    complex_data = np.array(rnd[0::2], dtype=np.complex64)
    complex_data.imag = rnd[1::2]
    return complex_data


def test_numpy_fft_speed(fft_size: int, iterations: int = 500) -> float:
    complex_data = create_test_data(fft_size)
    time_process_start = time.perf_counter()
    for test in range(iterations):
        _ = np.fft.fft(complex_data)
    time_process_end = time.perf_counter()
    return (1e6 * (time_process_end - time_process_start)) / iterations


def test_fftw_fft_speed(fft_size: int, iterations: int = 500, fftw_threads: int = 1) -> float:
    if pyfftw:
        complex_data = create_test_data(fft_size)
        time_process_start = time.perf_counter()
        kwargs = {'threads': fftw_threads}
        for test in range(iterations):
            _ = pyfftw.interfaces.numpy_fft.fft(complex_data, **kwargs)
        time_process_end = time.perf_counter()
        return (1e6 * (time_process_end - time_process_start)) / iterations
    return 1e6  # something very big in useconds


def test_scipy_fft_speed(fft_size: int, iterations: int = 500) -> float:
    if fftpack:
        complex_data = create_test_data(fft_size)
        time_process_start = time.perf_counter()
        for test in range(iterations):
            _ = fftpack.fft(complex_data)
        time_process_end = time.perf_counter()
        return (1e6 * (time_process_end - time_process_start)) / iterations
    return 1e6  # something very big in useconds


def convert_to_frequencies(bins: List[int], sample_rate: float, fft_size: int) -> List[float]:
    """
    Convert the sparse list of bins provided to a list of actual frequencies

    :param bins: A sparse list of bins from an fft, fftshift() already applied
    :param sample_rate: The sample rate in sps
    :param fft_size: The number of bins in the full fft
    :return: A list of frequencies
    """

    # map bins to frequencies, remember our bins are now +- values around zero
    bin_hz = sample_rate / fft_size
    freqs = [(bin_value - fft_size // 2) * bin_hz for bin_value in bins]
    return freqs


class Spectrum:
    def __init__(self, fft_size: int):
        """
        Initialisation with sensible defaults
        """
        self._fft_size = fft_size
        self._win = None
        self._fftw_threads = os.cpu_count() or 1
        self._use_scipy_fft = False
        self._use_fftw_fft = False
        self.set_fft()

    def set_fft(self):
        self._win = np.hamming(self._fft_size)

        # which fft to use, even though there is a difference it does not always carry through to exec times
        scipy_fft = test_scipy_fft_speed(self._fft_size, 500)
        numpy_fft = test_numpy_fft_speed(self._fft_size, 500)
        fftw_fft = test_fftw_fft_speed(self._fft_size, 500, self._fftw_threads)
        logger.debug(f"FFT {self._fft_size} scipy:{scipy_fft:0.1f}usec, "
                     f"numpy:{numpy_fft:0.1f}usec, "
                     f"fftw:{fftw_fft:0.1f}usec")
        self._use_scipy_fft = False
        self._use_fftw_fft = False
        if scipy_fft < numpy_fft and scipy_fft < fftw_fft:
            self._use_scipy_fft = True
            logger.debug(" - Using scipy for fft")
        elif numpy_fft < scipy_fft and numpy_fft < fftw_fft:
            logger.debug(" - Using numpy for fft")
        else:
            self._use_fftw_fft = True
            logger.debug(" - Using fftw for fft")

    # @profile
    def mag_spectrum(self, complex_samples: np.array, reorder: bool = True) -> np.ndarray:
        """Perform an fft of the samples with windowing applied and return the magnitudes
        Note that the returned magnitudes have been reordered

        :param complex_samples: The complex samples to use
        :param reorder: Re-order the result so that array is -ve to +ve with zero in the middle
        :return: The magnitude of the fft, NOT normalised to fft size
            """

        # check that the fft size has not changed
        if complex_samples.size != self._fft_size:
            self._fft_size = complex_samples.size
            self.set_fft()

        # normalisation by dividing by fft size not done here, faster elsewhere
        if self._use_scipy_fft:
            signals_fft = fftpack.fft(complex_samples * self._win)
        elif self._use_fftw_fft:
            kwargs = {'threads': self._fftw_threads}
            signals_fft = pyfftw.interfaces.numpy_fft.fft(complex_samples * self._win, **kwargs)
        else:
            signals_fft = np.fft.fft(complex_samples * self._win)

        if reorder:
            # this is quite expensive, longer than the fft() numpy ans scipy are the same
            signals_fft = np.fft.fftshift(signals_fft)
            # pyfftw is marginally faster but the test would blow away the gain
            # signals_fft = pyfftw.interfaces.numpy_fft.fftshift(signals_fft)

        # profiled and timed to find fastest way to get magnitude
        # there is a difference between abs() and conj - maybe 32/64bit floats ?
        # magnitudes = abs(np.fft.fftshift(signals_fft))  # not this updates signals_fft as well
        # magnitudes = abs(signals_fft)  # not this updates signals_fft as well
        magnitudes = (signals_fft * signals_fft.conj()).real

        return magnitudes
