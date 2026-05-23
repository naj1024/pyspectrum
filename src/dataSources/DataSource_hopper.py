"""
Test class for a frequency-hopping signal source.

Hops over a configurable list of frequencies with a dwell time and guard time.
The hop pattern is random but repeatable (seeded). Each hop has a random SNR.
The noise floor is constant; hop signals sit above it.

Parameters string format:
    seed:dwell_ms:guard_ms:freq_hz,freq_hz,...
    e.g. "42:20:5:-1000000,-500000,0,500000,1000000"

Frequencies are relative to centre frequency (baseband offsets in Hz).
"""

import logging
import math
import time
from typing import List, Tuple

import numpy as np
import numpy.typing as npt

from dataSources import DataSource

logger = logging.getLogger('spectrum_logger')

module_type = "simulated_hopper"
help_string = f"{module_type}:seed:dwell_ms:guard_ms:freq_hz,freq_hz,..."
web_help_string = "A test source with a frequency-hopping signal; random SNR per hop, constant noise floor"
import_error_msg = ""


def is_available() -> Tuple[str, str]:
    return module_type, import_error_msg


# Default hop frequencies as baseband offsets - so -1/2fs to 1/2fs
_DEFAULT_FREQS_HZ: List[float] = np.linspace(num=64, start=-0.5, stop=0.5)
_DEFAULT_SEED        = 42
_DEFAULT_DWELL_MS    = 345.0   # ms the signal is present
_DEFAULT_GUARD_MS    = 67.0    # ms of silence between hops
_DEFAULT_SNR_MIN_DB  = 15.0    # minimum per-hop SNR above noise floor (dB)
_DEFAULT_SNR_MAX_DB  = 25.0   # maximum per-hop SNR above noise floor (dB)


class Input(DataSource.DataSource):

    def __init__(self,
                 parameters: str,
                 data_type: str,
                 sample_rate: float,
                 centre_frequency: float,
                 input_bw: float):
        """
        Frequency-hopping test source.

        :param parameters: "seed:dwell_ms:guard_ms:freq_hz,freq_hz,..."
        :param data_type:  Not used (always 32fle internally)
        :param sample_rate: Sample rate in samples/sec
        :param centre_frequency: Centre frequency in Hz
        :param input_bw: Input filter bandwidth (informational)
        """
        self._constant_data_type = "32fle"

        if not parameters or parameters == "":
            parameters = f"{_DEFAULT_SEED}:{_DEFAULT_DWELL_MS}:{_DEFAULT_GUARD_MS}"

        super().__init__(parameters, self._constant_data_type, sample_rate, centre_frequency, input_bw)

        self._name = module_type
        self._connected = False
        self._gain_modes = ["manual"]
        super().set_gain_mode(self._gain_modes[0])
        super().set_help(help_string)
        super().set_web_help(web_help_string)

        self._adc_bits = 16

        # ------------------------------------------------------------------ #
        # Parse parameters
        # ------------------------------------------------------------------ #
        seed, dwell_ms, guard_ms, hop_freqs = self._parse_parameters(parameters)

        self._seed      = seed
        self._dwell_ms  = dwell_ms
        self._guard_ms  = guard_ms
        self._hop_freqs = hop_freqs          # baseband offsets in Hz

        self._hop_freqs_normalised = [f / self._sample_rate_sps for f in self._hop_freqs]

        self._update_rate_dependent_params()

        # ------------------------------------------------------------------ #
        # Noise floor calibration
        #
        # We want a constant noise floor in the final (post-_max_amp) signal.
        # The tone amplitude is then set per-hop to sit snr_db above that floor.
        #
        # Both tone and noise are generated in a normalised ±1 space and then
        # multiplied by _max_amp together, so SNR is preserved through that
        # scaling.  We therefore work entirely in the pre-scale space:
        #
        #   noise_std  = fixed value (per I or Q component, pre-scale)
        #   tone_amp   = noise_std * sqrt(2 * snr_linear)
        #                  where the factor of 2 converts from per-component
        #                  noise power (noise_std²) to total complex noise power
        #                  (2·noise_std²), matching a complex-exponential signal
        #                  of power tone_amp².
        #
        # _max_amp keeps everything well below ADC full scale.
        # ------------------------------------------------------------------ #
        self._max_amp = 0.1   # keep signals well below full-scale

        # Noise std chosen so the noise floor is clearly visible but not dominant.
        # At _max_amp=0.1 this gives a noise floor around -40 dBFS per sample,
        # which is a reasonable SDR-like noise level.
        self._noise_std = 0.05   # per I or Q component, in pre-scale space

        # ------------------------------------------------------------------ #
        # Hop-pattern RNG (seeded for repeatability)
        # ------------------------------------------------------------------ #
        self._rng = np.random.default_rng(self._seed)
        self._hop_order = self._rng.permutation(len(self._hop_freqs)).tolist()
        self._hop_index = 0   # position within the current permutation

        # ------------------------------------------------------------------ #
        # Per-hop state
        # ------------------------------------------------------------------ #
        self._current_hop_freq   = self._hop_freqs[self._hop_order[0]]
        self._current_snr_db     = self._rng.uniform(_DEFAULT_SNR_MIN_DB, _DEFAULT_SNR_MAX_DB)
        self._samples_in_phase   = 0      # samples generated in current phase
        self._in_guard           = False  # True → outputting silence (guard)
        self._osc_phase          = np.complex64(1 + 0j)

    def _update_rate_dependent_params(self) -> None:
        """Recompute sample-count parameters that depend on sample rate."""
        self._dwell_samples = int(round(self._sample_rate_sps * self._dwell_ms / 1000.0))
        self._guard_samples = int(round(self._sample_rate_sps * self._guard_ms / 1000.0))
        self._hop_freqs = [f * self._sample_rate_sps for f in self._hop_freqs_normalised]

        if hasattr(self, '_hop_order'):
            self._current_hop_freq = self._hop_freqs[self._hop_order[self._hop_index]]

        logger.info(
            f"Hop source rate update: dwell={self._dwell_ms}ms "
            f"({self._dwell_samples} samp), guard={self._guard_ms}ms "
            f"({self._guard_samples} samp) at {self._sample_rate_sps / 1e6:.3f} Msps,"
            f"freqs: {self._hop_freqs}"
        )

    def set_sample_rate_sps(self, sr: float) -> None:
        self._sample_rate_sps = sr
        self._update_rate_dependent_params()

    # ---------------------------------------------------------------------- #
    # Parameter parsing
    # ---------------------------------------------------------------------- #
    def _parse_parameters(self, parameters: str):
        """Return (seed, dwell_ms, guard_ms, hop_freqs)."""
        parts = parameters.split(":")
        try:
            seed     = int(parts[0])   if len(parts) > 0 else _DEFAULT_SEED
            dwell_ms = float(parts[1]) if len(parts) > 1 else _DEFAULT_DWELL_MS
            guard_ms = float(parts[2]) if len(parts) > 2 else _DEFAULT_GUARD_MS
        except (ValueError, IndexError):
            logger.error("Hop source: bad seed/dwell/guard, using defaults")
            seed, dwell_ms, guard_ms = _DEFAULT_SEED, _DEFAULT_DWELL_MS, _DEFAULT_GUARD_MS

        sr_2 = float(self._sample_rate_sps)
        hop_freqs = None
        if len(parts) > 3:
            try:
                hop_freqs = [float(f) * sr_2 for f in parts[3].split(",") if f.strip()]
            except ValueError:
                logger.error("Hop source: bad frequency list, using defaults")

        if hop_freqs is None:
            hop_freqs = [float(f) * sr_2 for f in _DEFAULT_FREQS_HZ]

        return seed, dwell_ms, guard_ms, hop_freqs

    # ---------------------------------------------------------------------- #
    # Hop sequencing helpers
    # ---------------------------------------------------------------------- #
    def _next_hop(self) -> None:
        """Advance to the next hop frequency and draw a new random SNR."""
        self._hop_index += 1
        if self._hop_index >= len(self._hop_order):
            # Reshuffle for the next round (still deterministic via seeded RNG)
            self._hop_order = self._rng.permutation(len(self._hop_freqs)).tolist()
            self._hop_index = 0

        self._current_hop_freq = self._hop_freqs[self._hop_order[self._hop_index]]
        self._current_snr_db   = float(self._rng.uniform(_DEFAULT_SNR_MIN_DB, _DEFAULT_SNR_MAX_DB))
        self._osc_phase        = np.complex64(1 + 0j)   # reset phase at each hop

    def _signal_amplitude_for_snr(self, snr_db: float, fft_size: int = 2048) -> float:
        """
        Return tone amplitude (pre-scale) that produces snr_db in an fft_size-point
        FFT display.

        FFT processing gain = N/2  (complex, one-sided noise reference).
        We pre-compensate so the displayed bin SNR matches snr_db.

            amp = noise_std * sqrt(2 * snr_linear / (fft_size / 2))
                = noise_std * sqrt(4 * snr_linear / fft_size)
        """
        snr_linear = 10 ** (snr_db / 10.0)
        fft_gain = fft_size / 2  # processing gain (linear power)
        return self._noise_std * math.sqrt(2.0 * snr_linear / fft_gain)

    # ---------------------------------------------------------------------- #
    # DataSource interface
    # ---------------------------------------------------------------------- #
    def open(self) -> bool:
        if import_error_msg:
            msgs = f"no {module_type} device available, {import_error_msg}"
            self._error = msgs
            logger.error(msgs)
            raise ValueError(msgs)

        if self._parameters == "?":
            self._error = f"Can't scan for {module_type} devices"
            return False

        logger.debug(f"Connected to {module_type} source")
        self._connected = True
        return self._connected

    def set_sample_type(self, data_type: str) -> None:
        super().set_sample_type(self._constant_data_type)

    def set_spectral_output(self, active: bool) -> None:
        self._spectral_output = active

    # ---------------------------------------------------------------------- #
    # Core sample generation
    # ---------------------------------------------------------------------- #
    def read_cplx_samples(self, number_samples: int) -> Tuple[npt.NDArray[np.complex64], float]:
        """
        Generate `number_samples` complex64 samples.

        The output is a mix of:
          • Dwell segments: tone at _current_hop_freq with random SNR above noise
          • Guard segments: noise only (silence between hops)

        Segments are stitched together to fill the requested buffer, so a
        single call may span multiple hop transitions.
        """
        sample_rate = self._sample_rate_sps
        output      = np.zeros(number_samples, dtype=np.complex64)
        cursor      = 0   # where in `output` we are writing

        while cursor < number_samples:
            remaining_in_call = number_samples - cursor

            if self._in_guard:
                # ---------------------------------------------------------- #
                # Guard period — noise only
                # ---------------------------------------------------------- #
                phase_budget = self._guard_samples - self._samples_in_phase
                n_seg = min(phase_budget, remaining_in_call)

                if n_seg <= 0:
                    self._samples_in_phase = 0
                    self._in_guard = False
                    self._next_hop()
                    continue

                noise = self._make_noise(n_seg)
                output[cursor:cursor + n_seg] = noise
                cursor                  += n_seg
                self._samples_in_phase  += n_seg

                if self._samples_in_phase >= self._guard_samples:
                    # Guard done → move to next hop
                    self._samples_in_phase = 0
                    self._in_guard         = False
                    self._next_hop()

            else:
                # ---------------------------------------------------------- #
                # Dwell period — tone + noise
                # ---------------------------------------------------------- #
                # Dwell period — tone + noise
                phase_budget = self._dwell_samples - self._samples_in_phase
                n_seg = min(phase_budget, remaining_in_call)

                if n_seg <= 0:
                    # Phase already exhausted (can happen after a sample-rate change);
                    # transition to guard immediately without generating samples.
                    self._samples_in_phase = 0
                    self._in_guard = True
                    continue

                freq = self._current_hop_freq
                amp = self._signal_amplitude_for_snr(self._current_snr_db, number_samples)
                phases = np.arange(n_seg, dtype=np.float64)
                tone = (self._osc_phase *
                        np.exp(1j * 2 * np.pi * freq / sample_rate * phases)
                        ).astype(np.complex64) * np.float32(amp)

                phase_step = np.complex64(np.exp(1j * 2 * np.pi * freq / sample_rate))
                self._osc_phase = tone[-1] / np.float32(amp) * phase_step  # safe: n_seg > 0

                noise   = self._make_noise(n_seg)
                segment = (tone + noise).astype(np.complex64)

                output[cursor:cursor + n_seg] = segment
                cursor                 += n_seg
                self._samples_in_phase += n_seg

                if self._samples_in_phase >= self._dwell_samples:
                    # Dwell done → enter guard
                    self._samples_in_phase = 0
                    self._in_guard         = True

        # ------------------------------------------------------------------ #
        # Scale and ADC quantisation (mirrors sweep source)
        # ------------------------------------------------------------------ #
        output *= np.float32(self._max_amp)
        output *= np.float32(10 ** (self._gain / 20.0))

        ADC_SCALE = np.float32(32767.0)
        i_int = np.clip(np.round(output.real * ADC_SCALE), -32768, 32767).astype(np.int16)
        q_int = np.clip(np.round(output.imag * ADC_SCALE), -32768, 32767).astype(np.int16)
        output = (i_int.astype(np.float32) + 1j * q_int.astype(np.float32)).astype(np.complex64)
        output /= ADC_SCALE

        rx_time = self.simulate_sample_wait_time(number_samples)
        return output, rx_time

    # ---------------------------------------------------------------------- #
    # Internal helpers
    # ---------------------------------------------------------------------- #
    def _make_noise(self, n: int) -> np.complex64:
        """Return n samples of complex AWGN at the fixed noise floor."""
        i = np.random.normal(0, self._noise_std, n).astype(np.float32)
        q = np.random.normal(0, self._noise_std, n).astype(np.float32)
        return (i + 1j * q).astype(np.complex64)