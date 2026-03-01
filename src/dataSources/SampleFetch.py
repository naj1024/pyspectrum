# Get samples to allow fft overlaps
#
# This was pretty much constructed from a chatgpt prompt
#

import numpy as np

from dataSources import DataSource
from misc import Sdr


class OverlapSampleFetch:
    # need to get overlapping samples each time
    def __init__(self, data_source: DataSource.DataSource, fft_size: int, sample_rate: float,
                 overlap_ratio: float = 0.5):
        if not (0 < overlap_ratio < 1):
            raise ValueError("Overlap_ratio must be between 0 and 1 (non-inclusive)")
        self.data_source = data_source
        self.fft_size = fft_size
        # how far we need to jump over
        self.hop_size = int(fft_size * (1 - overlap_ratio))
        self.buffer = np.array([], dtype=np.complex64)
        self.last_rx_time = None
        self.overlap = overlap_ratio
        self.sample_rate = sample_rate

    def get_next_block(self):
        while len(self.buffer) < self.fft_size:
            new_samples, rx_time = self.data_source.read_cplx_samples(self.hop_size)
            if new_samples is None or new_samples.size == 0:
                return None, None, self.hop_size

            if self.buffer.size == 0:
                # This is the time of the first sample going into the buffer
                self.last_rx_time = rx_time

            self.buffer = np.concatenate((self.buffer, new_samples))

        # Calculate timestamp of the first sample in this fft_block
        block_time = self.last_rx_time
        fft_block = self.buffer[:self.fft_size]

        # Drop hop_size samples from buffer (preserving overlap)
        self.buffer = self.buffer[self.hop_size:]

        # Advance the base time by hop duration for next block
        hop_duration_nsec = int((self.hop_size * 1e9) / self.sample_rate)
        self.last_rx_time += hop_duration_nsec

        return fft_block, block_time, self.hop_size


class BlockSampleFetch:
    # simple case where we get the fft size of samples each time
    def __init__(self, data_source: DataSource.DataSource, fft_size: int):
        self.data_source = data_source
        self.fft_size = fft_size

    def get_next_block(self):
        samples, rx_time = self.data_source.read_cplx_samples(self.fft_size)
        if samples is None or samples.size != self.fft_size:
            return None, None, 0
        return samples, rx_time, self.fft_size


class DynamicSampleFetch:
    def __init__(self, data_source: DataSource.DataSource, sdr_config: Sdr.Sdr):
        self.data_source = data_source
        self.sdr_config = sdr_config
        self.fetcher = None
        self.last_fft_size = None
        self.last_overlap = None

    def _check_config(self):
        fft_size = self.sdr_config.fft_size
        overlap = self.sdr_config.fft_overlap

        if fft_size != self.last_fft_size or overlap != self.last_overlap:
            self.fetcher = create_sample_fetch(self.data_source, self.sdr_config)
            self.last_fft_size = fft_size
            self.last_overlap = overlap

    def get_next_block(self):
        self._check_config()
        if self.fetcher:
            return self.fetcher.get_next_block()
        else:
            return None, None, 0


def create_sample_fetch(data_source: DataSource.DataSource, sdr_config: Sdr.Sdr):
    if sdr_config.fft_overlap == 0:
        # simple non-overlapping samples required
        return BlockSampleFetch(data_source, sdr_config.fft_size)
    elif 0 < sdr_config.fft_overlap < 100:
        # overlapping samples required
        overlap_ratio = sdr_config.fft_overlap / 100.0
        return OverlapSampleFetch(data_source, sdr_config.fft_size, sdr_config.sample_rate, overlap_ratio)
    else:
        raise ValueError(f"Unsupported FFT overlap: {sdr_config.overlap_percent}")
