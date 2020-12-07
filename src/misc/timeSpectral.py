import time
import random

import numpy as np

from misc import Variables
from dataSources import DataSource
from dataProcessing import ProcessSamples


def time_spectral(configuration: Variables):
    """
    Time how long it takes to compute various things and show results

    For FFT sizes Show results as max sps that would be possible all other things ignored
    :return: None
    """
    data_size = 2048
    # some random bytes, max of 4bytes per complex sample
    bytes_d = bytes([random.randrange(0, 256) for _ in range(0, data_size * 4)])
    print(f"data conversion time, 1Msps for 2048 samples is {data_size:0.1f}usec")
    print("data \tusec \tnsec/sample\ttype")
    print("===================================")
    for data_type in DataSource.supported_data_types:
        converter = DataSource.DataSource("null", data_size, data_type, 1e6, 1e6, 0)

        iterations = 1000
        time_start = time.perf_counter()
        for loop in range(iterations):
            _ = converter.unpack_data(bytes_d)
        time_end = time.perf_counter()

        processing_time = (time_end - time_start) / iterations
        processing_time_per_sample = processing_time / data_size
        print(f"{data_size} \t{processing_time * 1e6:0.1f} \t{processing_time_per_sample * 1e9:0.1f} \t\t{data_type}")

    # only measuring powers of two, not limited to that though
    fft_sizes = [256, 512, 1024, 2048, 4096, 8192, 16384, 32768]
    print("\nSpectral processing time (sps are absolute maximums for the basic spectral calculation)")
    print("spec \tusec  \tMsps")
    print("========================")
    for fft_size in fft_sizes:
        configuration.fft_size = fft_size
        processor = ProcessSamples.ProcessSamples(configuration)
        rands = np.random.rand(fft_size * 2)
        rands = rands - 0.5
        samples = np.array(rands[0::2], dtype=np.complex64)
        samples.imag = rands[1::2]

        iterations = 1000
        time_start = time.perf_counter()
        for loop in range(iterations):
            processor.process(samples)
        time_end = time.perf_counter()

        processing_time = (time_end - time_start) / iterations
        max_sps = fft_size / processing_time
        print(f"{fft_size} \t{processing_time * 1e6:0.1f} \t{max_sps / 1e6:0.3f}")
    print("")
