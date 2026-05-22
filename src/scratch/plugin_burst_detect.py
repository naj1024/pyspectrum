import logging
import math
import textwrap
import time

import numpy as np

from misc.PluginManager import Plugin

# testing - for plotting some test points
# from misc.ArrayPlotter import ArrayPlotter
# plotter = (ArrayPlotter(ylim=(-80,50)))

logger = logging.getLogger('spectrum_logger')

default_threshold = 100.0  # very large to stop any burst detects unless we use --plugin option
help_string = textwrap.dedent(f'''
              Analysis type plugin. 
                Finds bursts between x-min and y-max long.
                Takes options:
                   --plugin analysis:burst:threshold:10 
                   --plugin analysis:burst:enabled:on 
                   --plugin analysis:burst:min_msec:10 
                   --plugin analysis:burst:max_msec:100 
                default threshold: {default_threshold}dB
                default enabled:off
                default min_msec:10
                default max_msec:100''')


class BurstDetect(Plugin):
    def __init__(self, **kwargs):
        # Note we need to have a class method for each entry in the self_methods list
        # and the name has to match
        self._methods = ['analysis']
        self._enabled = True
        self._threshold = 8.0  # default_threshold
        self._threshold_on = self._threshold
        self._threshold_off = self._threshold - 2.0  # hysteresis
        self._min_msec = 10
        self._max_msec = 10000
        self._help_string = help_string

        self._fast = None
        self._slow = None

        self._alpha_fast = 0.6
        self._alpha_slow = 0.995

        self._min_bins = 3
        self._hang_frames = 2

        self._state = "IDLE"
        self._frame_count = 0
        self._start_frame = 0
        self._last_active_frame = 0

        self._burst_bin_hits = None  # accumulates activity per bin
        self._cluster_gap_bins = 2  # allow small gaps between bins
        self._min_cluster_bins = 2  # reject single-bin noise

        self._burst_fast_accum = None
        self._burst_slow_accum = None

        self._centre_frequency = 0
        self._parse_options(kwargs)

    def _parse_options(self, options: dict) -> None:
        """
        Parse the given dictionary of options to see if there is anything for us
        :param options: Dictionary of stuff, note that these are NOT the command line args but derived from them
        :return: None
        """
        if "plugin_options" in options:
            for opts in options["plugin_options"]:
                if len(opts):
                    opt = opts[0]
                    parts = [x.strip() for x in opt.split(':')]
                    if len(parts) == 4:
                        # --plugin analysis:peak:threshold:10
                        if parts[0] == "analysis" and parts[1] == "burst" and parts[2] == "threshold":
                            self._threshold = float(parts[3])

                        # --plugin analysis:peak:enabled:on
                        if parts[0] == "analysis" and parts[1] == "burst" and parts[2] == "enabled":
                            if parts[3] == "on":
                                self._enabled = True
                            else:
                                self._enabled = False

    def help(self):
        """
        return the help string for this plugin
        :return: The help string, pre-formatted
        """
        return self._help_string

    def _cluster_bins(self, hit_counts, sample_rate_sps, fft_size, centre_frequency, reordered):
        active = hit_counts > 0
        indices = np.where(active)[0]

        if len(indices) == 0:
            return []

        clusters = []
        current_cluster = [indices[0]]

        for idx in indices[1:]:
            if idx - current_cluster[-1] <= self._cluster_gap_bins:
                current_cluster.append(idx)
            else:
                clusters.append(current_cluster)
                current_cluster = [idx]

        clusters.append(current_cluster)

        # Convert clusters → frequency ranges
        bin_width = sample_rate_sps / fft_size
        results = []

        for cluster in clusters:
            if len(cluster) < self._min_cluster_bins:
                continue

            c = np.array(cluster)

            # --- Frequency mapping ---
            if reordered:
                freqs = (c - fft_size // 2) * bin_width
            else:
                freqs = np.where(
                    c < fft_size // 2,
                    c * bin_width,
                    (c - fft_size) * bin_width
                )

            f_min = freqs.min() + centre_frequency
            f_max = freqs.max() + centre_frequency
            f_center = freqs.mean() + centre_frequency

            # --- SNR calculation ---
            fast_vals = self._burst_fast_accum[c]
            slow_vals = self._burst_slow_accum[c]

            # --- Best: total energy SNR ---
            snr_linear_cluster = np.sum(fast_vals) / (np.sum(slow_vals) + 1e-15)
            snr_db_cluster = 10.0 * np.log10(snr_linear_cluster + 1e-15)

            snr = float(snr_db_cluster)

            results.append({
                "f_min": float(f_min),
                "f_max": float(f_max),
                "f_center": float(f_center),
                "bw": float(f_max-f_min),
                "bins": int(len(cluster)),
                "snr_db": snr
            })

        return results

    def analysis(self, magnitudes_squared: np.ndarray,
                 noise_floors: np.ndarray,
                 overlap: float,
                 sample_rate_sps: float,
                 centre_frequency: float,
                 reordered: bool = False) -> (bool, []):

        if not self._enabled:
            return False, []

        print(self._state)
        n_bins = len(magnitudes_squared)

        # --- Init trackers if required ---
        if (self._fast is None or len(self._fast) != n_bins) or self._centre_frequency != centre_frequency:
            self._fast = magnitudes_squared.copy()
            self._slow = magnitudes_squared.copy()
            self._state = "IDLE"
            self._frame_count = 0
            self._burst_bin_hits = np.zeros(n_bins, dtype=np.int32)
            self._centre_frequency = centre_frequency
            self._burst_fast_accum = np.zeros(n_bins, dtype=np.float64)
            self._burst_slow_accum = np.zeros(n_bins, dtype=np.float64)
            self._burst_slow_accum = np.zeros(n_bins, dtype=np.float64)

        # --- Fast / Slow tracking ---
        self._fast = self._alpha_fast * self._fast + (1 - self._alpha_fast) * magnitudes_squared

        # alpha = self._alpha_slow if self._state == "IDLE" else 0.9999
        # self._slow = alpha * self._slow + (1 - alpha) * magnitudes_squared

        # # Only update slow when NOT in burst (prevents swallowing bursts)
        # if self._state == "IDLE":
        #     self._slow = self._alpha_slow * self._slow + (1 - self._alpha_slow) * magnitudes_squared

        # only update where no strong signal, linear not dB
        linear_threshold = 10 ** (self._threshold / 10)
        mask = self._fast < (self._slow * linear_threshold)
        self._slow[mask] = (
                self._alpha_slow * self._slow[mask]
                + (1 - self._alpha_slow) * magnitudes_squared[mask]
        )

        # --- SNR ---
        snr_db = 10*np.log10(self._fast) - 10*np.log10(self._slow)

        # plotter.update(10*np.log10(self._fast), 10*np.log10(self._slow), snr_db, 10*np.log10(magnitudes_squared))

        if self._state == "IDLE":
            detections = snr_db > self._threshold_on
        else:
            detections = snr_db > self._threshold_off

        active_bins = np.count_nonzero(detections)
        frame_active = active_bins >= self._min_bins

        # --- Time handling (overlap aware) ---
        fft_size = n_bins
        hop_size = int(fft_size * (1.0 - overlap / 100))
        hop_size = max(hop_size, 1)

        frame_period_sec = hop_size / sample_rate_sps
        frame_period_ms = frame_period_sec * 1000.0

        min_frames = int(self._min_msec / frame_period_ms)
        max_frames = int(self._max_msec / frame_period_ms)

        event_detected = False
        clusters = []

        # --- Burst tracking state machine ---
        if frame_active:
            self._last_active_frame = self._frame_count

        if self._state == "IDLE" and frame_active:
            self._start_frame = self._frame_count
            self._state = "IN_BURST"
            self._burst_bin_hits[:] = 0  # reset accumulator
            self._burst_fast_accum[:] = 0.0
            self._burst_slow_accum[:] = 0.0

        elif self._state == "IN_BURST":
            self._burst_bin_hits += detections.astype(np.int32)
            # accumulate linear power
            self._burst_fast_accum += self._fast
            self._burst_slow_accum += self._slow

            if (self._frame_count - self._last_active_frame) > self._hang_frames:

                end_frame = self._last_active_frame
                duration_frames = end_frame - self._start_frame

                if min_frames <= duration_frames <= max_frames:
                    event_detected = True

                    clusters = self._cluster_bins(
                        self._burst_bin_hits,
                        sample_rate_sps,
                        fft_size,
                        centre_frequency,
                        reordered
                    )

                    # Flatten to center freqs
                    event_freqs = [(c["f_center"]) / 1e6 for c in clusters]
                    event_freqs.sort()

                self._state = "IDLE"

        self._frame_count += 1

        if event_detected:
            now = time.time()
            try:
                print(
                    f"detected {(duration_frames * frame_period_ms):.2f} msec {time.strftime('%H:%M:%S', time.gmtime(now))}",
                    max(clusters, key=lambda x: x['snr_db']))
            except Exception as e:
                print(e)

        return event_detected, clusters
