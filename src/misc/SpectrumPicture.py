"""
From a file of digitised samples produce a spectral picture

Run through the file with fft and peak detect on the magnitudes
Produce a small png file that can be displayed in the web UI
The png filename will be the input filename with .png appended

"""
import os
import pathlib

from dataProcessing import Spectrum
from dataSources import DataSource_file

import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import matplotlib.image as image


class SpectrumPicture:

    def __init__(self, thumbnail_dir: str):
        self._fft_size = 2048
        self._thumbnail_dir = thumbnail_dir
        matplotlib.use('Agg')

    def create_picture(self, filename: pathlib.PurePath):
        spec = Spectrum.Spectrum(self._fft_size, Spectrum.get_windows()[0])
        peaks_squared = np.full(self._fft_size, -200)
        try:
            file_str = str(filename)
            source = DataSource_file.Input(file_str, self._fft_size, "16tle", 1.0, 0.0, 1.0)
            source.set_rewind(False)
            source.set_sleep(False)
            ok = source.open()
            count = 0
            while ok:
                try:
                    samples, _ = source.read_cplx_samples()
                    count += 1
                    mags_squared = spec.mag_spectrum(samples, True)
                    peaks_squared = np.maximum.reduce([mags_squared, peaks_squared])
                except ValueError:
                    ok = False  # end of file
                except OSError:
                    ok = False  # end of file

            source.close()

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
                image.thumbnail(str(pic_name), str(thumb_name), scale=0.10)  # unix won't take pathlib for this

        except ValueError as msg:
            raise ValueError(msg)
