"""
From a file of digitised samples produce a spectral picture

Run through the file with fft and peak detect on the magnitudes
Produce a small png file that can be displayed in the web UI
The png filename will be the input filename with .png appended

"""
import os
import pathlib

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
        self._thumbnail_dir = thumbnail_dir
        if matplotlib:
            matplotlib.use('Agg')

    def create_picture(self, filename: pathlib.PurePath) -> bool:
        if not matplotlib:
            return False

        try:
            file_str = str(filename)
            # let's assume that it is going to be 16tle
            source = DataSource_file.Input(file_str, "16tle", 1.0, 0.0, 1.0)
            source.set_rewind(False)
            source.set_sleep(False)
            ok = source.open()

            # can't produce spectrums if we don't know what the file samples are
            if source.has_meta_data():
                spec = Spectrum.Spectrum(self._fft_size, Spectrum.get_windows()[0])
                peaks_squared = np.full(self._fft_size, -200)
                count = 0
                while ok:
                    try:
                        samples, _ = source.read_cplx_samples(self._fft_size)
                        count += 1
                        mags_squared = spec.mag_spectrum(samples, True)
                        peaks_squared = np.maximum.reduce([mags_squared, peaks_squared])
                    except ValueError:
                        ok = False  # end of file
                    except OSError:
                        ok = False  # end of file

                if count > 0:
                    powers = Spectrum.get_powers(peaks_squared)
                    average = np.average(powers)
                    maximum = np.max(powers)
                    # set everything below average to the average
                    np.clip(powers, average, maximum, out=powers)

                    plt.clf()
                    pic_name = pathlib.PurePath(file_str + ".png")
                    fig, ax = plt.subplots()
                    f = np.arange(0, self._fft_size, 1)
                    ax.plot(f, powers)
                    ax.set_xticks([])
                    ax.set_yticks([])
                    fig.savefig(pic_name)
                    # create a thumbnail for the web
                    thumb_name = pathlib.PurePath(self._thumbnail_dir, os.path.basename(filename) + ".png")
                    matplotlib.image.thumbnail(str(pic_name), str(thumb_name), scale=0.10)  # unix won't take pathlib

            source.close()

        except ValueError as msg:
            raise ValueError(msg)

        return True
