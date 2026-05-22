"""
ArrayPlotter — non-blocking, tick-driven live plotter for 4 ndarrays.

Usage
-----
    from ArrayPlotter import ArrayPlotter

    plotter = ArrayPlotter()

    while True:
        plotter.update(a, b, c, d)          # draw + pump GUI events, returns fast
        # ... rest of your loop ...
"""

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

# ── Configuration ─────────────────────────────────────────────────────────────
N_POINTS = 512
LABELS   = ["Channel A", "Channel B", "Channel C", "Channel D"]
COLORS   = ["#00e5ff", "#ff4081", "#76ff03", "#ffffff"]
YLIM     = (0, 1.0)   # adjust to your magnitude range


class ArrayPlotter:
    """
    Lightweight, non-blocking plotter.
    Call update(arr1, arr2, arr3, arr4) in your own loop — no plt.show() needed.
    """

    def __init__(
        self,
        n_points: int = N_POINTS,
        labels: list[str] = LABELS,
        colors: list[str] = COLORS,
        ylim: tuple[float, float] = YLIM,
        title: str = "FFT Live Monitor",
    ):
        self.n    = n_points
        self.x    = np.arange(n_points)
        self.ylim = ylim

        plt.style.use("dark_background")
        plt.ion()                          # interactive mode — no blocking show()

        self.fig = plt.figure(figsize=(12, 7), facecolor="#0a0a0f")
        self.fig.suptitle(title, color="#e0e0e0", fontsize=14, fontweight="bold", y=0.97)

        gs = GridSpec(4, 1, figure=self.fig, hspace=0.45,
                      left=0.07, right=0.97, top=0.92, bottom=0.06)

        self._axes  = []
        self._lines = []
        self._fills = []

        for i, (label, color) in enumerate(zip(labels, colors)):
            ax = self.fig.add_subplot(gs[i])
            ax.set_facecolor("#0d0d18")
            ax.set_xlim(0, n_points)
            ax.set_ylim(*ylim)
            ax.set_ylabel("Magnitude", color="#888", fontsize=8)
            ax.set_title(label, color=color, fontsize=10, loc="left", pad=3)
            ax.tick_params(colors="#555", labelsize=7)
            for spine in ax.spines.values():
                spine.set_edgecolor("#222")
            if i == 2:
                ax.set_xlabel("FFT Bin", color="#888", fontsize=8)

            zeros = np.zeros(n_points)
            line, = ax.plot(self.x, zeros, color=color,
                            linewidth=0.9, antialiased=True)
            fill  = ax.fill_between(self.x, 0, zeros, color=color, alpha=0.15)

            self._axes.append(ax)
            self._lines.append(line)
            self._fills.append(fill)

        self.fig.canvas.draw()
        plt.pause(0.0001)                   # show the window immediately

    # ── public API ────────────────────────────────────────────────────────────

    def update(
        self,
        arr1: np.ndarray,
        arr2: np.ndarray,
        arr3: np.ndarray,
        arr4: np.ndarray,
    ) -> bool:
        """
        Push new FFT data and redraw. Returns False if the window was closed
        (so you can break your loop gracefully).
        """
        if not plt.fignum_exists(self.fig.number):
            return False

        arrays = [arr1, arr2, arr3, arr4]
        colors = [l.get_color() for l in self._lines]

        for i, (ax, line, color, arr) in enumerate(
            zip(self._axes, self._lines, colors, arrays)
        ):
            y = np.asarray(arr, dtype=float)[:self.n]

            line.set_ydata(y)

            self._fills[i].remove()
            self._fills[i] = ax.fill_between(self.x, 0, y,
                                              color=color, alpha=0.15)

        self.fig.canvas.draw_idle()        # queue a redraw (non-blocking)
        self.fig.canvas.flush_events()     # pump GUI events, returns fast

        return True

    @property
    def is_open(self) -> bool:
        return plt.fignum_exists(self.fig.number)


# ── Demo — run this file directly to see it in action ─────────────────────────
if __name__ == "__main__":
    plotter = ArrayPlotter()
    phase   = 0.0
    x       = np.linspace(0, 1, N_POINTS)

    while plotter.is_open:
        phase += 0.08

        a = (np.abs(np.sin(2 * np.pi * (x - phase * 0.3) * 4))
             * np.exp(-((x - 0.25) ** 2) / 0.02)
             + np.random.rand(N_POINTS) * 0.04)

        b = (np.abs(np.sin(2 * np.pi * (x + phase * 0.5) * 6))
             * np.exp(-((x - 0.55) ** 2) / 0.03)
             + np.random.rand(N_POINTS) * 0.04)

        c = (np.abs(np.sin(2 * np.pi * (x - phase * 0.2) * 9))
             * np.exp(-((x - 0.75) ** 2) / 0.025)
             + np.random.rand(N_POINTS) * 0.04)

        d = (np.abs(np.sin(2 * np.pi * (x - phase * 0.2) * 19))
             * np.exp(-((x - 0.75) ** 2) / 0.01)
             + np.random.rand(N_POINTS) * 0.04)

        plotter.update(a, b, c, d)