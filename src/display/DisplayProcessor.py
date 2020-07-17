import multiprocessing
import math
import queue

from display import Display

MAX_DISPLAY_QUEUE_DEPTH = 20


def nearest_multiple_of_10(num: float) -> float:
    if not math.isinf(num) and num != math.nan:
        low = (num // 10) * 10
        high = low + 10
        # Return of closest of the two
        return high if num - low > high - num else low
    return 0.0


class DisplayProcessor(multiprocessing.Process):
    """
    Class that wraps the Display class up in something we can run as a separate process

    We take data in from a Queue and pass it to the display
    We assume (!) that the queue will hold a Tuple of (spec, peak, threshold, annotations)
    The spec, peak and threshold will be of length display_width (the fft size)
    The annotations is a sparse list of bins we wish to show as being masked out
    """

    def __init__(self,
                 name: str,
                 data_queue: multiprocessing.Queue,
                 control_queue: multiprocessing.Queue,
                 display_width: int,
                 sps: float,
                 centre_frequency: float,
                 spectrogram_flag: bool):
        """

        :param name: A string that will be appended to the window title of the display
        :param data_queue: Where we get our data from
        :param control_queue: For controls back from the display
        :param display_width: The number of elements in the display, i.e. the fft size
        :param sps: The digitisation rate in sps
        :param centre_frequency: The supposed centre frequency in Hz
        :param spectrogram_flag: Do we want a spectrogram or not
        """
        multiprocessing.Process.__init__(self)
        self._exit_now = multiprocessing.Event()

        self._name = name

        self._data_queue = data_queue
        self._control_queue = control_queue
        self._spectrogram_flag = spectrogram_flag

        # the following, display_width, sps and centre frequency may change on the fly
        self._display_width = display_width
        self._sps = sps
        self._centre_frequency = centre_frequency

    def shutdown(self) -> None:
        """
        Shutdown the display server. This is called shutdown() to duplicate the socket shutdown method

        :return: None
        """
        self._exit_now.set()

    def run(self):
        # wait on the first set of data so we can scale the axes correctly
        _, sps, centre, spec, peak, time_start, time_end = self._data_queue.get()

        # find nearest integer of ten to the mean
        # nearest_mean = nearest_multiple_of_10(float(np.mean(spec)))
        nearest_mean = -40

        # The display must be created here to make it mutable?
        display = self.create_display(self._display_width, self._sps, self._centre_frequency, nearest_mean)

        display_on = True

        # The only thing that should now change on the display
        # are the contents of the individual traces
        while display_on and not self._exit_now.is_set():
            try:
                display_on, sps, centre, spec, peak, time_start, time_end = self._data_queue.get(timeout=0.1)

                if display_on:
                    # TODO: fix this annoying feature
                    #  If the width changes then destroy the current display and create a new one
                    #  just can't get the width to change without and exception in the old display
                    #  bit of a sledge hammer approach.
                    if spec.size != self._display_width:
                        display.close_display()
                        display = self.create_display(spec.size, sps, centre, nearest_mean)

                    display_on = display.plot(sps, centre, spec, peak, time_start, time_end)
            except queue.Empty:
                # will end up here a lot due to the timeout on the queue read
                display.keep_display_responsive()

        print("Display process exited")
        return

    def create_display(self, display_width, sps, centre, nearest_mean):
        self._sps = sps
        self._centre_frequency = centre
        self._display_width = display_width

        # 50dB initial range
        display = Display.Display(self._name, self._display_width, self._sps, self._centre_frequency,
                                  nearest_mean - 10, nearest_mean + 40.0,
                                  self._spectrogram_flag)
        return display
