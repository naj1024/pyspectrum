"""
From a file of digitised samples produce a spectral picture

Run through the file with fft and peak detect on the magnitudes
Produce a small png file that can be displayed in the web UI
The png filename will be the input filename with .png appended

"""
import logging
import os
import pathlib
from matplotlib import image

import numpy as np

from dataProcessing import Spectrum
from dataSources import DataSource_file

# may not have matplotlib, broken matplotlib on ubuntu 20.04 LTS
try:
    import matplotlib
except ImportError:
    matplotlib = None

if matplotlib:
    import matplotlib.pyplot as plt


def can_create_pictures() -> bool:
    if matplotlib:
        return True
    return False


class SpectrumPicture:

    def __init__(self, thumbnail_dir: str):
        self._fft_size = 2048
        self._number_ffts = 500
        self._spectrogram_pic = True
        self._thumbnail_dir = thumbnail_dir
        if matplotlib:
            matplotlib.use('Agg')

        self._spec = Spectrum.Spectrum(512, 'Hanning')

    def create_picture(self, filename: pathlib.PurePath) -> bool:
        if not matplotlib:
            return False

        try:
            file_str = str(filename)
            # let's assume that it is going to be 16tle and 1Msps, opening the file may be able to correct these values
            source = DataSource_file.Input(file_str, "16tle", 1.0e6, 0.0, 1.0e6)
            source.set_rewind(False)
            source.set_throttle(False)
            ok = source.open()

            # Produce spectrum even if we don't know what the file samples are in
            # Otherwise we will continualy try again
            if True:  # source.has_meta_data():
                spec = Spectrum.Spectrum(self._fft_size, Spectrum.get_windows()[0])
                peaks_squared = np.full(self._fft_size, -200)
                powers = []
                count = 0
                while ok:
                    try:
                        samples, _ = source.read_cplx_samples(self._fft_size)
                        mag = spec.mag_spectrum(samples, True)
                        powers.append(self._spec.get_powers(mag, source.get_sample_rate_sps(), False, 0))
                        peaks_squared = np.maximum.reduce([mag, peaks_squared])
                        count += 1
                    except ValueError:
                        ok = False  # end of file
                    except OSError:
                        ok = False  # end of file

                    # after x many fft's we probably have a good peak spectrum to make an image of
                    if count > self._number_ffts:
                        ok = False

                if count > 0:
                    pic_name = pathlib.PurePath(self._thumbnail_dir, os.path.basename(filename) + ".png")

                    if self._spectrogram_pic:
                        powers = np.array(powers)
                        spec = powers.T
                        max_db = np.max(spec)
                        spec = np.clip(spec, max_db - 40, max_db)  # dB range
                        plt.imshow(spec, aspect='auto', origin='lower', cmap='gray_r')
                        plt.axis('off')
                        plt.savefig(pic_name, dpi=50, bbox_inches='tight', pad_inches=0)
                    else:
                        powers = self._spec.get_powers(peaks_squared, source.get_sample_rate_sps(), False, 0)
                        average = np.average(powers)
                        maximum = np.max(powers)
                        # set everything below average to the average
                        np.clip(powers, average, maximum, out=powers)

                        plt.clf()
                        fig, ax = plt.subplots()
                        f = np.arange(0, self._fft_size, 1)
                        ax.plot(f, powers)
                        ax.set_xticks([])
                        ax.set_yticks([])
                        fig.savefig(pic_name)
                        plt.close(fig)

            source.close()

        except ValueError as msg:
            raise ValueError(msg)

        return True
