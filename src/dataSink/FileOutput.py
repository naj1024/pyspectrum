import queue
import numpy as np

from misc import SnapVariables


class FileOutput:
    """
    Simple wrapper class for writing binary data to file
    """

    def __init__(self):
        self._centre_freq_hz = 0
        self.sample_rate_sps = 0
        self._file = None
        self._bytes_per_sample = 4  # We will ALWAYS output 16tle as we are on little endian machines
        self._record_time_in_seconds = 0
        self._prerecord_time_in_seconds = 0
        self._write_samples = 0

    def open(self, config: SnapVariables, centre_frequency_hz: float, sample_rate_sps: float) -> None:
        """
        :param config: How the snap is configured
        :param centre_frequency_hz: Where we are currently tuned to
        :param sample_rate_sps: What the current sample rate is
        :return:
        """
        self._centre_freq_hz = centre_frequency_hz
        self.sample_rate_sps = sample_rate_sps
        if self._record_time_in_seconds:
            # create the filename we will use
            filename = config.baseFilename + f".cf{self._centre_frequency_hz / 1e6:.6f}" \
                                                f".cplx.{self._sample_rate_sps:.0f}.16tle"
            print(f"Record filename: {filename}")
            self._file = open(filename, "wb")

    def close(self) -> None:
        """Close the file"""
        if self._file:
            self._file.close()

    def write(self, data: np.array) -> int:
        """
        Write the data to the file

        :param data: To write, complex floating point values
        :return: Number of samples we tried to write
        """

        if self._file:
            # this is messy as we wish to write out 16tle and we have floating point complex samples
            converted_data = np.empty(shape=(1, 2 * data.size), dtype="int16")[0]
            index_out = 0
            data *= 32768  # scale to max of int16 type, as we know we are already limited to +-1 on inputs
            for val in data:
                converted_data[index_out] = np.int16(val.real)
                converted_data[index_out + 1] = np.int16(val.imag)
                index_out += 2

            _ = converted_data.tofile(self._file)

        return data.size

    def record_data(self,
                    data: np.array,
                    start: bool) -> bool:
        """
        Record complex samples and if start is true begin writing them to file
        As we need to write samples that happen before start begins we need to
        remember samples all the time, to the pre event depth and write
        that data out first when the start happens

        :param data: Blocks of complex samples
        :param start: true if we should start writing data out
        :return: Boolean flag to say we finished
        """
        # Are we trying to record
        finished: bool = False
        if self._record_time_in_seconds:
            # Do we need to start
            if start and self._write_samples <= 0:
                print("Record start")

                # set the number of samples we need to write
                self._write_samples = self._record_time_in_seconds * self._sample_rate

                # do we have any pre event to save off first
                if self._prerecord_time_in_seconds:
                    while not pre_event_data.empty():
                        self.write(pre_event_data.get())

                # now for the current data, deal with different input formats
                if type(data[0]) == np.complex64:
                    self._write_samples = 0
                    pass
                elif type(data[0]) == np.complex128:
                    self._write_samples = 0
                    pass
                else:
                    self._write_samples -= self.write(data)
                if self._write_samples <= 0:
                    print("Record end")
                    finished = True

            elif self._write_samples > 0:
                # continue writing, even if events are zero
                self._write_samples -= self.write(data)
                if self._write_samples <= 0:
                    print("Record end")
                    finished = True

        return finished
