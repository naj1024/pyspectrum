import logging
import time
from typing import List

import numpy as np
import numpy.typing as npt

# import line_profiler

logger = logging.getLogger('spectrum_logger')

try:
    import scipy
    from scipy import fftpack
    from scipy import signal
except ImportError:
    fftpack = None
    signal = None
    logger.info("No scipy support in environment")

try:
    import pyfftw  # seems best suited for large FFT sizes, >8192

    pyfftw.interfaces.cache.enable()  # planner cache
    pyfftw.interfaces.cache.set_keepalive_time(5)  # keep fftw things cache alive for 5 seconds between calls
except ImportError:
    pyfftw = None
    logger.info("Warning: No fftw support in environment")


def create_test_data(size: int) -> npt.NDArray[np.complex64]:
    rnd = np.random.rand(size * 2)
    complex_data = np.array(rnd[0::2], dtype=np.complex64)
    complex_data.imag = rnd[1::2]
    return complex_data


def test_numpy_fft_speed(complex_data: npt.NDArray[np.complex64], iterations: int = 500) -> float:
    t1 = time.perf_counter()
    for i in range(iterations):
        signals_fft = np.fft.fft(complex_data)
        signals_fft = np.fft.fftshift(signals_fft)
        _ = (signals_fft * signals_fft.conj()).real
    t2 = time.perf_counter()
    return (1e6 * (t2 - t1)) / iterations


def test_fftw_fft_speed(complex_data: npt.NDArray[np.complex64], iterations: int = 500, _fftw_threads: int = 1) -> float:
    if pyfftw:
        pyfftw.interfaces.cache.enable()
        pyfftw.interfaces.cache.set_keepalive_time(10)
        pyfftw.config.NUM_THREADS = 1    # things get worse with more threads - for me
        t1 = time.perf_counter()
        for i in range(iterations):
            signals_fft = pyfftw.interfaces.numpy_fft.fft(complex_data)
            signals_fft = np.fft.fftshift(signals_fft)
            _ = (signals_fft * signals_fft.conj()).real
        t2 = time.perf_counter()
        return (1e6 * (t2 - t1)) / iterations
    return 10e6  # something very big in useconds


def test_scipy_fft_speed(complex_data: npt.NDArray[np.complex64], iterations: int = 500) -> float:
    if fftpack:
        t1 = time.perf_counter()
        for i in range(iterations):
            signals_fft = fftpack.fft(complex_data)
            signals_fft = np.fft.fftshift(signals_fft)
            _ = (signals_fft * signals_fft.conj()).real
        t2 = time.perf_counter()
        return (1e6 * (t2 - t1)) / iterations
    return 10e6  # something very big in useconds


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

def get_windows() -> list[str]:
    if fftpack:
        return ['Hanning', 'Hamming', 'Blackman', 'Bartlett', 'Kaiser_16', 'Rectangular', 'Flattop']
    else:
        # no flat top
        return ['Hanning', 'Hamming', 'Blackman', 'Bartlett', 'Kaiser_16', 'Rectangular']


class Spectrum:
    def __init__(self, fft_size: int, window: str):
        """
        Initialisation with sensible defaults
        """
        self._fft_size = fft_size
        self._win = None
        self._use_scipy_fft = False
        self._use_fftw_fft = False

        self._window_gain_compensation = 1.0
        self._effective_noise_bw = 1.0

        self._window_type = None
        self.set_window(window)
        self.set_fft()

        logger.info(f"Spectrum {self._fft_size}, "
                    f"{self._window_type}, "
                    f"{1.0}sps, "
                    f"enbw {self.get_enbw():.3f}, "
                    f"rbw {self.get_rbw(1):.6f}Hz per sps")

    def set_fft_size(self, fft_size: int):
        self._fft_size = fft_size
        self.set_fft()

    def set_window(self, window: str) -> None:
        # window_gain_compensation values adjusted by matching the
        # rectangular window average power on the spectrum
        try:
            N = self._fft_size
            win = window.lower()
            if win in (w.lower() for w in get_windows()):
                self._window_type = window
                if self._window_type == 'Rectangular':
                    self._win = np.ones(N)
                elif self._window_type == 'Flattop':
                    if signal:
                        self._win = signal.windows.flattop(N, False)
                    else:
                        raise ValueError()
                elif self._window_type == 'Hanning':
                    self._win = np.hanning(N)
                elif self._window_type == 'Hamming':
                    self._win = np.hamming(N)
                elif self._window_type == 'Blackman':
                    self._win = np.blackman(N)
                elif self._window_type == 'Kaiser_16':
                    self._win = np.kaiser(N, 16)
                elif self._window_type == 'Bartlett':
                    self._win = np.bartlett(N)
                else:
                    raise ValueError()

                if self._win is not None:
                    self._window_gain_compensation = np.mean(self._win)
                    self._effective_noise_bw = N * np.sum(self._win ** 2) / (np.sum(self._win) ** 2)

            else:
                raise ValueError()
        except ValueError:
            # default window is hanning
            self._win = np.hanning(self._fft_size)
            self._window_gain_compensation = np.mean(self._win)
            self._effective_noise_bw = N * np.sum(self._win ** 2) / (np.sum(self._win) ** 2)
            self._window_type = "Hanning"
            logging.error(f"Unavailable window {window}, defaulting to Hanning")

        logger.info(f"Spectrum {self._fft_size}, "
                    f"{self._window_type}, "
                    f"{1.0}sps, "
                    f"enbw {self.get_enbw():.3f}, "
                    f"rbw {self.get_rbw(1):.6f}Hz per sps")

    def get_window(self) -> str:
        return self._window_type

    def get_fft_size(self) -> int:
        return self._fft_size

    def get_fft_used(self) -> str:
        if self._use_scipy_fft:
            return "scipy"
        elif self._use_fftw_fft:
            return "fftw"
        else:
            return "numpy"

    def get_enbw(self) -> float:
        return self._effective_noise_bw

    def get_rbw(self, sps: float) -> float:
        return (sps /  self._fft_size) * self._effective_noise_bw

    def set_fft(self) -> None:
        """
        Decide which fft to use for the required fft length
        Implementations are very specific to how the underlying libraries are compiled and implemented

        :return: None
        """
        self.set_window(self._window_type)

        # which fft to use
        # even though there is a difference it does not always carry through to exec times
        complex_data = create_test_data(self._fft_size)
        scipy_fft = test_scipy_fft_speed(complex_data, 500)
        logger.debug(f"FFT {self._fft_size} scipy:{scipy_fft:0.1f}usec")
        numpy_fft = test_numpy_fft_speed(complex_data, 500)
        logger.debug(f"FFT {self._fft_size} numpy:{numpy_fft:0.1f}usec")
        fftw_fft = test_fftw_fft_speed(complex_data, 500)
        logger.debug(f"FFT {self._fft_size} fftw:{fftw_fft:0.1f}usec")
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
    def mag_spectrum(self, complex_samples_in: npt.NDArray[np.complex64], reorder: bool = True) -> np.ndarray:
        """Perform the fft on the samples with windowing applied and return the magnitudes
        Note that the returned magnitudes have been reordered

        :param complex_samples_in: The complex samples to use
        :param reorder: Re-order the result so that array is -ve to +ve with zero in the middle
        :return: The magnitude of the fft, NOT normalised to fft size
            """

        # check that the fft size has not changed
        if complex_samples_in.size != self._fft_size:
            self._fft_size = complex_samples_in.size
            self.set_fft()

        # normalisation by dividing by fft size not done here,
        # do it when we convert to dB in get_powers()
        if self._win is not None:
            # illegal values in array will cause problems, which we may have as the wrong input type could be selected
            # e.g. 16bit selected as floats
            complex_samples = np.nan_to_num(complex_samples_in.astype(np.complex64)) * \
                              np.nan_to_num(self._win.astype(np.complex64))
        else:
            complex_samples = complex_samples_in.copy()

        if self._use_scipy_fft:
            signals_fft = fftpack.fft(complex_samples)
        elif self._use_fftw_fft:
            signals_fft = pyfftw.interfaces.numpy_fft.fft(complex_samples)
        else:
            signals_fft = np.fft.fft(complex_samples)

        if reorder:
            # this is quite expensive, longer than the fft() numpy and scipy are the same
            # do it once when we send data to UI, on peak detected multiple fft results
            signals_fft = np.fft.fftshift(signals_fft)
            # pyfftw is marginally faster but the test would blow away the gain
            # signals_fft = pyfftw.interfaces.numpy_fft.fftshift(signals_fft)

        # profiled and timed to find fastest way to get magnitude
        # magnitudes = abs(np.fft.fftshift(signals_fft))  # note this updates signals_fft as well
        # magnitudes = abs(signals_fft)  # note this updates signals_fft as well
        magnitudes_squared = signals_fft.real**2 + signals_fft.imag**2

        return magnitudes_squared

    def get_powers(self, mag_squared: np.ndarray, sps: float, psd: bool, offset: float) -> np.ndarray:
        """
        Return the dB powers of a magnitude squared fft output

        Plot type	                                Signal peak effect	        Noise floor effect
        =============================================================================================
        Bin power (dB per FFT bin, RBW corrected)	unchanged with FFT/window	changes with RBW
        PSD (dB/Hz)	                                changes with FFT/window	    unchanged per Hz

        :param mag_squared:
        :param sps: The sample rate in Hz
        :param psd: True is output is to be psd, db/Hz
        :param offset: dbm offset
        :return: dB array of the magnitudes squared
        """
        # convert to dB and normalise,
        N = len(mag_squared)
        if psd:
            # normalize for PSD (dB/Hz)
            psd_vals = mag_squared / (N * sps * self._window_gain_compensation** 2 * self._effective_noise_bw)
        else:
            # normalize for bin power (dB per FFT bin)
            rbw = sps / N * self._effective_noise_bw
            psd_vals = rbw * mag_squared / (N * self._window_gain_compensation** 2)  # linear bin power

        psd_vals = 10 * np.log10(psd_vals + 1e-20) - offset  # avoid log(0) with 1e-20

        return psd_vals


