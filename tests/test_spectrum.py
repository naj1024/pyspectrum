from numpy import allclose
from numpy import array
from numpy import complex64

from dataProcessing import Spectrum


def test_magnitude():
    # two values per complex sample
    raw_samples = [1.0, 1.0, 0.5, 0.25, 0.25, -0.25, 0.5, -0.5]
    complex_samples = array(raw_samples[::2], dtype=complex64)
    complex_samples.imag = raw_samples[1::2]
    spectrum = Spectrum.Spectrum(complex_samples.size, Spectrum.get_windows()[0])  # length is in complex samples
    powers = spectrum.mag_spectrum(complex_samples)
    expected = [0.09348125, 0.50033125, 0.48810625, 0.01965625]
    assert allclose(powers, expected)
