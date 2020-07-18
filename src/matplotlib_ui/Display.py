import time
from typing import Tuple

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import backend_bases
import matplotlib

SPECTROGRAM_DEPTH: int = 200
DEFAULT_OFF_SCALE_INITIAL_VALES = -200.0


# wraparound array holding nanosecond start / end times
class Timestamps:
    def __init__(self, depth: int):
        self._start_times = [0] * depth
        self._end_times = [0] * depth
        self._depth: int = depth

    def add(self, time_start: float, time_end: float) -> None:
        # move everyone down
        self._start_times = [time_start] + self._start_times[0:-1]
        self._end_times = [time_end] + self._end_times[0:-1]

    def get(self, index) -> Tuple[float, float]:
        index = index % self._depth
        return self._start_times[index], self._end_times[index]


class Display:
    """A simple class to matplotlib_ui data

    TODO: Can't handle changes to width while running
    """

    def __init__(self,
                 name: str,
                 width: int,
                 sps: float,
                 centre_frequency: float,
                 min_db: float,
                 max_db: float,
                 spectrogram_flag: bool):
        """
        The initialisation of a Display
        :param name: A string that will be appended to the window title string
        :param width: The number of points on the x axes
        :param sps: The digitisation rate used
        :param centre_frequency: The centre of the spectrum in Hz
        :param min_db: The minimum dB we will scale for
        :param max_db: The maximum dB we will scale for
        :param spectrogram_flag: Spectrogram displayed as well as spectrum, slows things down a lot
        """

        # Timings for use of blit animation - stalls under windows 10
        # timings for 1024 fft at 600ksps from Pluto
        # realtime is 1.7msec which would need 585fps
        #
        # method    windows         linux (in VM)
        # =============================================
        # draw()    23msec 43fps    20-60msec 16-50fps
        # blit()    8msec  125fps   8-40msec  25-125fps

        # not sure if we need this forcing of the TkAgg backend
        if matplotlib.get_backend() != "TkAgg":
            print("Changing matplotlib_ui backend from: ", matplotlib.get_backend())
            matplotlib.use("TkAgg")
            print("Display backend now: ", matplotlib.get_backend())

        # things that define our matplotlib_ui window
        self._window_title = f"Spectrum Analyser from {name}"
        self._display_width = width
        self._sps = sps
        self._centre_frequency = centre_frequency
        self._max_y = max_db
        self._min_y = min_db
        self._spectrogram_flag = spectrogram_flag

        # holds timestamps of the rows on the spectrogram
        self._spectrogram_times = Timestamps(SPECTROGRAM_DEPTH)

        # things that are set by mouse actions in the window
        self._pause_spectrogram = False
        self._spectrogram_shift = 0.0

        # set the max_hold trace to a very low value
        self._max_powers = np.full(self._display_width, DEFAULT_OFF_SCALE_INITIAL_VALES)
        self._max_hold = False

        # set the average trace to the middle of the range
        self._average_powers = np.full(self._display_width, (min_db + (max_db - min_db) / 2))

        # x axes unit and scale for displayed values
        self._x_scale = 1
        self._x_units = "Hz"
        self._x_res = 0
        self.set_x_units()

        # a nice string that says what the matplotlib_ui properties are
        info_str = self.get_window_info_string()

        self._max_freq = 0
        self._min_freq = 0
        self._figure = None
        self._spectrums = None
        self._spectrogram = None
        self._figure, self._spectrums, self._spectrogram = self.create_plots()

        self.set_spectrum_bits(info_str)

        self._spectrum_trace, self._peak_trace, self._max_hold_trace, self._average_trace = self.create_traces()

        # show a legend for the different traces
        self._legend = self._spectrums.legend(loc='upper left')

        # Allow clicking on the legend to control visibility of traces
        self._lined = dict()
        self.set_legend_up()

        # add the spectrogram
        if self._spectrogram_flag:
            self._spectrogram_history = SPECTROGRAM_DEPTH
            self._spectrogram_min = self._min_y
            self._spectrogram_max = self._max_y
            self._spectrogram_data = np.full((self._spectrogram_history, self._display_width), self._spectrogram_min)
            self._spectrogram_im = None
            self.create_spectrogram()

        # plot the figure, but don't block
        plt.show(block=False)
        self._figure.canvas.draw()
        self._figure.canvas.flush_events()

    def set_legend_up(self):
        lines = [self._spectrum_trace, self._peak_trace, self._max_hold_trace, self._average_trace]
        for legend_line, original_line in zip(self._legend.get_lines(), lines):
            legend_line.set_picker(7)  # 7 pts tolerance around the lines
            self._lined[legend_line] = original_line
        # click and pick events
        self._figure.canvas.mpl_connect('button_press_event', self._process_click)
        self._figure.canvas.mpl_connect('scroll_event', self._process_scroll)
        self._figure.canvas.mpl_connect('pick_event', self._process_legend_click)

    def create_traces(self):
        # initial trace contents, so that we can use  use set_ydata() to update the matplotlib_ui
        x_values = np.linspace(self._min_freq, self._max_freq, self._display_width)
        y_values = np.full(self._display_width, self._max_y)
        spectrum_trace = self._spectrums.plot(x_values, y_values, ls='-', lw=1, label='live', color='blue')[0]
        peak_trace = self._spectrums.plot(x_values, y_values, ls='-', lw=1, label='peak', color='orange')[0]
        max_hold_trace = self._spectrums.plot(x_values, y_values, ls='-', lw=1, label='pk-hold', color='red')[0]
        average_trace = self._spectrums.plot(x_values, y_values, ls='-', lw=1, label='average', color='green')[0]
        return spectrum_trace, peak_trace, max_hold_trace, average_trace

    def create_spectrogram(self):
        # NOTE updates to the spectrogram are NOT constant time between, they vary according to
        # the input queue depth giving different fps. Could be difficult to make it a proper time on the Y-axes
        self._spectrogram_im = self._spectrogram.imshow(self._spectrogram_data,
                                                        cmap='Greys',
                                                        vmin=self._spectrogram_min,
                                                        vmax=self._spectrogram_max,
                                                        extent=[self._min_freq, self._max_freq,
                                                                self._spectrogram_history, 0],
                                                        aspect='auto',
                                                        interpolation='none',
                                                        resample=False)
        self._spectrogram.grid(False)
        # turn off labels and ticks on spectrogram
        self._spectrogram.tick_params(axis='y',  # changes apply to the x-axis
                                      which='both',  # both major and minor ticks are affected
                                      bottom=True,  # ticks along the bottom edge
                                      top=False,  # ticks along the top edge
                                      left=False,  # ticks on left
                                      right=False,  # ticks on right
                                      labelbottom=True,  # labels along the bottom edge
                                      labelleft=False  # labels off on left
                                      )

    def new_create_plots(self):
        # create matplotlib figure and subplots
        number = self._window_title
        # use previous figure number if we have one
        if self._figure:
            number = plt.gcf().number
        if self._spectrogram_flag:
            figure = plt.figure(figsize=(9, 5), num=number)
            if self._spectrums:
                spectrums = self._spectrums
            else:
                spectrums = plt.subplot(211)

            if self._spectrogram:
                spectrogram = self._spectrogram
            else:
                spectrogram = plt.subplot(212, sharex=spectrums)

            plt.subplots_adjust(bottom=0.06, left=0.07, right=0.95, top=0.94, hspace=0.16)
        else:
            figure = plt.figure(figsize=(9, 3), num=number)
            if self._spectrums:
                spectrums = self._spectrums
            else:
                spectrums = plt.axes()
            spectrogram = None
            plt.subplots_adjust(bottom=0.08, left=0.07, right=0.95, top=0.92, hspace=0.16)

        return figure, spectrums, spectrogram

    def create_plots(self):
        # create matplotlib figure and subplots

        # remove the pan and subplot buttons on the toolbar
        backend_bases.NavigationToolbar2.toolitems = (
            ('Home', 'Reset original view', 'home', 'home'),
            ('Back', 'Back to  previous view', 'back', 'back'),
            ('Forward', 'Forward to next view', 'forward', 'forward'),
            (None, None, None, None),
            # ('Pan', 'Pan axes with left mouse, zoom with right', 'move', 'pan'),
            ('Zoom', 'Zoom to rectangle', 'zoom_to_rect', 'zoom'),
            # ('Subplots', 'Configure subplots', 'subplots', 'configure_subplots'),
            (None, None, None, None),
            ('Save', 'Save the figure', 'filesave', 'save_figure')
        )

        if self._spectrogram_flag:
            figure = plt.figure(figsize=(9, 5), num=self._window_title)
            spectrums = plt.subplot(211)
            spectrogram = plt.subplot(212, sharex=spectrums)
            plt.subplots_adjust(bottom=0.06, left=0.07, right=0.95, top=0.94, hspace=0.16)
        else:
            figure = plt.figure(figsize=(9, 3), num=self._window_title)
            spectrums = plt.subplot(111)
            spectrogram = None
            plt.subplots_adjust(bottom=0.08, left=0.07, right=0.95, top=0.92, hspace=0.16)

        return figure, spectrums, spectrogram

    def set_spectrum_bits(self, title: str):
        # spectrum Y axis units
        self._spectrums.set_ylabel('dB', rotation=0)
        self._spectrums.set_title(title)

        # get the Hz range
        self._max_freq = ((self._sps // 2) + self._centre_frequency) / self._x_scale
        self._min_freq = ((-self._sps // 2) + self._centre_frequency) / self._x_scale

        # absolute width and height of plot area, removes guards around plot provided by plot()
        self._spectrums.set_xlim((self._min_freq, self._max_freq))
        self._spectrums.set_ylim(self._min_y, self._max_y)

        # grid on the spectrum
        self._spectrums.grid(True)

    def get_window_info_string(self):
        # basic information about the spectral matplotlib_ui
        # work out a sensible value for displaying the RBW
        bw, bw_units, rbw, rbw_units = self.set_bw_units()
        return f'CF:{(self._centre_frequency / self._x_scale):0.{self._x_res}f}' \
               f'{self._x_units}, BW:{bw:.1f}{bw_units}, RBW:{rbw:.0f}{rbw_units}'

    def set_bw_units(self):
        bw = self._sps / 1e6
        bw_units = "MHz"
        if bw < 0.9:
            bw *= 1000
            bw_units = "kHz"
        rbw = self._sps / (1000.0 * self._display_width)
        rbw_units = "kHz"
        if rbw < 0.9:
            rbw *= 1000
            rbw_units = "Hz"
        return bw, bw_units, rbw, rbw_units

    def set_x_units(self):
        if self._centre_frequency >= 900e6:
            self._x_scale = 1e9
            self._x_units = "GHz"
            self._x_res = 6
        elif self._centre_frequency >= 900e3:
            self._x_scale = 1e6
            self._x_units = "MHz"
            self._x_res = 3

    def _update_display_window(self, width: int, sps: float, centre: float, avg: float):
        # delete the current trace contents
        y_values = np.full(self._display_width, self._max_y)
        self._spectrum_trace.set_ydata(y_values)
        self._peak_trace.set_ydata(y_values)

        # start from scratch on all the plots
        self._display_width = width
        self._sps = sps
        self._centre_frequency = centre

        # reset the traces
        self._max_powers = np.full(self._display_width, DEFAULT_OFF_SCALE_INITIAL_VALES)
        self._average_trace.set_ydata(self._max_powers)
        self._max_hold_trace.set_ydata(self._max_powers)
        self._max_hold = False

        # reset the peak hold and averages
        self._max_powers = np.full(self._display_width, DEFAULT_OFF_SCALE_INITIAL_VALES)
        self._average_powers = np.full(self._display_width, avg)

        self.set_x_units()
        info_str = self.get_window_info_string()
        self._figure, self._spectrums, self._spectrogram = self.new_create_plots()
        self.set_spectrum_bits(info_str)
        self._spectrum_trace, self._peak_trace, self._max_hold_trace, self._average_trace = self.create_traces()
        if self._spectrogram_flag:
            self._spectrogram_data = np.full((self._spectrogram_history, self._display_width), self._spectrogram_min)
            self._spectrogram_im = None
            self.create_spectrogram()

        self.set_legend_up()

        # plot the figure, but don't block
        plt.show(block=False)
        self._figure.canvas.draw()
        self._figure.canvas.flush_events()

    def close_display(self):
        plt.close(self._figure)

    def keep_display_responsive(self) -> None:
        """
        Used to keep the matplotlib_ui responding to mouse events when we have no update_plot()
        :return: None
        """
        if plt.fignum_exists(self._figure.number):
            self._figure.canvas.draw()
            self._figure.canvas.flush_events()

    def plot(self, sps: float, centre: float, current: np.ndarray,
             peak_detected: np.ndarray, time_start: float, time_end: float) -> bool:
        """
        Plot the data

        If the flag is set then the second data are plotted with a dashed line

        :param sps: The digitisation rate in sps
        :param centre: The centre frequency in Hz
        :param current: The main data to plot
        :param peak_detected: The peak detect
        :param time_start: Time that this spectrum starts
        :param time_end: Time that this spectrum ends
        :return: True if matplotlib_ui is still present
        """

        if current.size != self._display_width or sps != self._sps or centre != self._centre_frequency:
            self._update_display_window(current.size, sps, centre, float(np.mean(current)))

        # figure will not exist if user closes its window
        if plt.fignum_exists(self._figure.number):
            self._spectrum_trace.set_ydata(current)
            self._peak_trace.set_ydata(peak_detected)

            # average, EWMA 0.01 is around 100
            alpha = 0.01
            # average of the instantaneous trace not the peaks
            self._average_powers = (1 - alpha) * self._average_powers + alpha * current
            self._average_trace.set_ydata(self._average_powers)

            # max hold functionality
            if self._max_hold:
                self._max_powers = np.maximum.reduce([peak_detected, self._max_powers])
            elif self._max_powers[0] != DEFAULT_OFF_SCALE_INITIAL_VALES:
                # don't want to do this every time round
                self._max_powers = np.full(self._display_width, DEFAULT_OFF_SCALE_INITIAL_VALES)
            self._max_hold_trace.set_ydata(self._max_powers)

            if self._spectrogram_flag and not self._pause_spectrogram:
                # update the times
                self._spectrogram_times.add(time_start, time_end)
                # move all lines down one and add new one to top
                # don't update if paused, this means click in the graph for power level etc will work correctly
                # there may be a faster way to do this, this method was best out of 5 types on stack exchange
                tmp_sp = np.empty_like(self._spectrogram_data)
                tmp_sp[:1] = peak_detected + self._spectrogram_shift
                tmp_sp[1:] = self._spectrogram_data[:-1]
                self._spectrogram_data = tmp_sp
                self._spectrogram_im.set_data(self._spectrogram_data)

            # print(current.shape, peak_detected.shape, self._average_powers.shape,
            #       self._max_powers.shape, self._spectrogram_data.shape)
            self._figure.canvas.draw()
            self._figure.canvas.flush_events()

        return plt.fignum_exists(self._figure.number)

    def _process_click(self, event):
        # Which graph one we are in
        if event.inaxes is None:
            self._legend.set_visible(not self._legend.get_visible())
        elif event.inaxes is self._spectrums:
            if event.button == 1 and event.xdata:
                print(f'Point = {event.xdata:0.{self._x_res}f}{self._x_units},{event.ydata:0.1f}dB')
            elif event.button == 2:
                self._annotations_visible = not self._annotations_visible
            elif event.button == 3:
                self._max_hold = not self._max_hold
        elif event.inaxes is self._spectrogram:
            if event.button == 1 and event.xdata:
                row_entry = int(event.ydata)
                row_start_time, row_end_time = self._spectrogram_times.get(row_entry)
                row_time_width_usec = (row_end_time - row_start_time) / 1e3
                secs = int(row_start_time / 1e9)
                micro_secs = ((row_start_time / 1e9) - secs) * 1000
                happened_at = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(secs)),

                # convert horizontal from frequency to bin number as graph knows frequency
                bin_entry = int((event.xdata * self._x_scale - self._centre_frequency) / (
                        self._sps / self._display_width) + self._display_width // 2)
                level = self._spectrogram_data[row_entry, bin_entry]
                level -= self._spectrogram_shift
                print(
                    f'Point = {event.xdata:0.{self._x_res}f}{self._x_units},{level:0.1f}dB, '
                    f'{happened_at[0]} and {micro_secs:0.0f}usec / {row_time_width_usec:0.0f}usec')
            elif event.button == 2:
                self._spectrogram_shift = 0.0
            elif event.button == 3 and event.xdata:
                self._pause_spectrogram = not self._pause_spectrogram
        else:
            self._legend.set_visible(not self._legend.get_visible())

    def _process_scroll(self, event):
        if event.inaxes is self._spectrums:
            y_min, y_max = self._spectrums.get_ylim()
            y_mid = y_min + (y_max - y_min) / 2
            if event.ydata > y_mid:
                if event.button == "down":
                    self._max_y -= 5
                elif event.button == "up":
                    self._max_y += 5
            else:
                if event.button == "down":
                    self._min_y -= 5
                elif event.button == "up":
                    self._min_y += 5
            if self._min_y > (self._max_y - 10):
                self._min_y = self._max_y - 10
            self._spectrums.set_ylim(self._min_y, self._max_y)
            #  self.add_spectrogram() gets slower and slower for some reason
        elif event.inaxes is self._spectrogram:
            if event.button == "up":
                self._spectrogram_shift -= 1.0
            elif event.button == "down":
                self._spectrogram_shift += 1.0

    def _process_legend_click(self, event):
        # if the legend is visible then we can change the visibility of traces
        if self._legend.get_visible():
            # on the pick event, find the trace corresponding to the
            # legend line, and toggle the visibility of that trace
            legend_line = event.artist
            trace = self._lined[legend_line]
            visible = not trace.get_visible()
            trace.set_visible(visible)
            # visual indication on legend line to indicate trace visibility
            if visible:
                legend_line.set_alpha(1.0)
            else:
                legend_line.set_alpha(0.2)
            self._figure.canvas.draw()


if __name__ == '__main__':
    Display("test", 1024, 10000.0, 0.0, -40.0, -10.0, False)

