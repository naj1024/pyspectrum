import logging
import textwrap
import time
import numpy as np

from misc.PluginManager import Plugin

logger = logging.getLogger('spectrum_logger')

default_threshold = 100.0

# testing - for plotting some test points
# from misc.ArrayPlotter import ArrayPlotter
# plotter = (ArrayPlotter(ylim=(-80,50)))

help_string = textwrap.dedent(f'''
Analysis type plugin.
Finds bursts between x-min and y-max long.

Options:
  --plugin analysis:burst:threshold:10
  --plugin analysis:burst:enabled:on

Defaults:
  threshold: {default_threshold} dB
  enabled: off
  min_msec: 10
  max_msec: 100
''')


class BurstDetect(Plugin):
    def __init__(self, **kwargs):
        self._methods = ['analysis']

        self._enabled = False
        self._threshold = 12.0

        self._min_msec = 10
        self._max_msec = 500

        self._alpha_fast = 0.6
        self._alpha_slow = 0.9

        self._min_bins = 2
        self._hang_frames = 3

        self._cluster_gap_bins = 2
        self._min_cluster_bins = 2

        self._fast = None
        self._slow = None

        self._burst_bin_hits = None
        self._burst_fast_accum = None
        self._burst_slow_accum = None

        self._state = "IDLE"
        self._frame_count = 0
        self._start_frame = 0
        self._last_active_frame = 0

        self._stuck_counter = None

        self._bin_ema = 0.0
        self._centre_frequency = 0

        self._help_string = help_string

        self._parse_options(kwargs)

    # -------------------------
    # Options
    # -------------------------
    def _parse_options(self, options: dict):
        if "plugin_options" in options:
            for opts in options["plugin_options"]:
                if not opts:
                    continue

                parts = [x.strip() for x in opts[0].split(':')]

                if len(parts) != 4:
                    continue

                if parts[:3] == ["analysis", "burst", "threshold"]:
                    self._threshold = float(parts[3])

                if parts[:3] == ["analysis", "burst", "enabled"]:
                    self._enabled = parts[3] == "on"

    def help(self):
        return self._help_string

    # -------------------------
    # Clustering
    # -------------------------
    def _cluster_bins(self, hit_counts, sample_rate_sps, fft_size, centre_frequency, reordered):
        indices = np.where(hit_counts > 0)[0]
        if len(indices) == 0:
            return []

        clusters = []
        current = [indices[0]]

        for idx in indices[1:]:
            if idx - current[-1] <= self._cluster_gap_bins:
                current.append(idx)
            else:
                clusters.append(current)
                current = [idx]

        clusters.append(current)

        bin_width = sample_rate_sps / fft_size
        results = []

        for cluster in clusters:
            if len(cluster) < self._min_cluster_bins:
                continue

            c = np.array(cluster)

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

            fast_vals = self._burst_fast_accum[c]
            slow_vals = self._burst_slow_accum[c]

            snr_linear = np.sum(fast_vals) / (np.sum(slow_vals) + 1e-15)
            snr_db = 10 * np.log10(snr_linear + 1e-15)

            results.append({
                # "f_min": float(f_min),
                # "f_max": float(f_max),
                "f_center": float(f_center),
                "bw": float(f_max - f_min),
                "bins": int(len(cluster)),
                "snr_db": float(snr_db)
            })

        return results

    # -------------------------
    # Main analysis
    # -------------------------
    def analysis(self, magnitudes_squared: np.ndarray,
                 overlap: float,
                 sample_rate_sps: float,
                 centre_frequency: float,
                 reordered: bool = False):

        if not self._enabled:
            return False, []

        n_bins = len(magnitudes_squared)

        # --- Init ---
        if (self._fast is None or len(self._fast) != n_bins
                or self._centre_frequency != centre_frequency):

            self._fast = magnitudes_squared.copy()
            self._slow = magnitudes_squared.copy()

            self._burst_bin_hits = np.zeros(n_bins, dtype=np.int32)
            self._burst_fast_accum = np.zeros(n_bins)
            self._burst_slow_accum = np.zeros(n_bins)

            self._state = "IDLE"
            self._frame_count = 0
            self._bin_ema = 0.0
            self._centre_frequency = centre_frequency

            self._stuck_counter = np.zeros(n_bins, dtype=np.int32)


        # --- Fast EMA ---
        self._fast = self._alpha_fast * self._fast + (1 - self._alpha_fast) * magnitudes_squared

        # --- Stable slow update ---
        snr_linear = self._fast / (self._slow + 1e-15)
        # --- normal noise update ---
        noise_mask = snr_linear < 4.0

        self._slow[noise_mask] = (
                self._alpha_slow * self._slow[noise_mask]
                + (1 - self._alpha_slow) * magnitudes_squared[noise_mask]
        )

        # --- recovery for stuck bins ---
        stuck = snr_linear > 10.0

        self._stuck_counter[stuck] += 1
        self._stuck_counter[~stuck] = 0

        reset_mask = self._stuck_counter > 50

        self._slow[reset_mask] = self._fast[reset_mask]
        self._stuck_counter[reset_mask] = 0

        # --- tiny global leak (optional but nice) ---
        self._slow += 0.0002 * (magnitudes_squared - self._slow)

        # --- SNR ---
        snr_db = 10 * np.log10(snr_linear)

        #plotter.update(10*np.log10(self._fast), 10*np.log10(self._slow), snr_db, 10*np.log10(magnitudes_squared))

        # --- Hysteresis ---
        if self._state == "IDLE":
            detections = snr_db > self._threshold
        else:
            detections = snr_db > (self._threshold - 2.0)

        active_bins = np.count_nonzero(detections)

        # --- Smooth bin count ---
        self._bin_ema = 0.7 * self._bin_ema + 0.3 * active_bins
        frame_active = self._bin_ema >= self._min_bins

        # --- Timing ---
        fft_size = n_bins
        hop_size = max(int(fft_size * (1.0 - overlap / 100)), 1)

        frame_period_ms = (hop_size / sample_rate_sps) * 1000.0
        min_frames = int(self._min_msec / frame_period_ms)
        max_frames = int(self._max_msec / frame_period_ms)

        event_detected = False
        clusters = []

        # --- Track activity ---
        if frame_active:
            self._last_active_frame = self._frame_count

        # --- State machine ---
        if self._state == "IDLE":
            if frame_active:
                self._start_frame = self._frame_count
                self._state = "IN_BURST"

                self._burst_bin_hits[:] = 0
                self._burst_fast_accum[:] = 0
                self._burst_slow_accum[:] = 0

        elif self._state == "IN_BURST":
            self._burst_bin_hits += detections.astype(np.int32)
            self._burst_fast_accum += self._fast
            self._burst_slow_accum += self._slow

            burst_length = self._frame_count - self._start_frame

            end_by_silence = (self._frame_count - self._last_active_frame) >= self._hang_frames
            end_by_timeout = burst_length >= max_frames

            # if end_by_timeout:
            #     print("LONG SIGNAL - ending")

            if end_by_silence or end_by_timeout:

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

                self._state = "IDLE"

        self._frame_count += 1

        if event_detected:
            now = time.time()
            try:
                print(
                    f"detected {(duration_frames * frame_period_ms):.2f} ms "
                    f"{time.strftime('%H:%M:%S', time.gmtime(now))}",
                    max(clusters, key=lambda x: x['snr_db'])
                )
            except Exception:
                pass

        return event_detected, clusters