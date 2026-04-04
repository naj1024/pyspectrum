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

    def __init__(self):
        self._fft_size = 512
        self._number_ffts = 2000
        if matplotlib:
            matplotlib.use('Agg')

        self._spec = Spectrum.Spectrum(512, 'Hanning')

    def create_picture(self,
                       full_data_filename: pathlib.PurePath,
                       destination_path: pathlib.PurePath) -> bool:
        if not matplotlib:
            return False

        try:
            file_str = str(full_data_filename)
            # let's assume that it is going to be 16tle and 1Msps, opening the file may be able to correct these values
            source = DataSource_file.Input(file_str, "16tle", 1.0e6, 0.0, 1.0e6)
            source.set_rewind(False)
            source.set_throttle(False)
            ok = source.open()

            # Produce spectrum even if we don't know what the file samples are in
            # Otherwise we will continually try again
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
                    pic_name = pathlib.PurePath(destination_path, os.path.basename(full_data_filename) + ".png")

                    plt.clf()
                    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6, 4))

                    # --- TOP: Spectrum ---
                    powers_spec = self._spec.get_powers(peaks_squared, source.get_sample_rate_sps(), False, 0)
                    average = np.average(powers_spec)
                    maximum = np.max(powers_spec)
                    np.clip(powers_spec, average, maximum, out=powers_spec)

                    f = np.arange(0, self._fft_size, 1)
                    ax1.plot(f, powers_spec)
                    ax1.set_xticks([])
                    ax1.set_yticks([])

                    # --- BOTTOM: Spectrogram ---
                    powers = np.array(powers)
                    spec = powers.T

                    max_db = np.max(spec)
                    avg_db = np.average(spec)
                    range_db = max_db - avg_db - 5
                    spec = np.clip(spec, max_db - range_db, max_db)

                    ax2.imshow(spec, aspect='auto', origin='lower', cmap='Blues')
                    ax2.set_xticks([])
                    ax2.set_yticks([])

                    # --- Save to file ---
                    plt.tight_layout(pad=0.1)
                    fig.savefig(pic_name, dpi=50, bbox_inches='tight', pad_inches=0)
                    plt.close(fig)

            source.close()

        except ValueError as msg:
            raise ValueError(msg)

        return True
