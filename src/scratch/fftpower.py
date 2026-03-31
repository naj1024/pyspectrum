import numpy as np
import matplotlib.pyplot as plt

fs = 1.024e3  # sample rate 1 kHz
t = np.arange(0, 1, 1 / fs)
f_sig = 100  # signal frequency
x = np.sin(2 * np.pi * f_sig * t)

fft_lengths = [256, 1024]
windows = {'Rect': np.ones, 'Hann': np.hanning}

plt.figure(figsize=(12, 6))

for N in fft_lengths:
    for wname, wfunc in windows.items():
        w = wfunc(N)
        CG = np.mean(w)
        ENBW = N * np.sum(w ** 2) / (np.sum(w) ** 2)

        X = np.fft.rfft(x[:N] * w)
        mag2 = np.abs(X) ** 2

        # PSD (dB/Hz)
        psd = mag2 / (N * fs * CG ** 2 * ENBW)
        psd_db = 10 * np.log10(psd + 1e-20)

        # Bin power (RBW corrected)
        rbw = fs / N * ENBW
        bin_power = mag2 / (N * CG ** 2) * 1  # linear bin power
        bin_power_db = 10 * np.log10(bin_power + 1e-20)

        freqs = np.fft.rfftfreq(N, 1 / fs)

        # Plot PSD
        plt.plot(freqs, psd_db, label=f'PSD {wname} N={N}', linestyle='--')
        # Plot Bin power
        plt.plot(freqs, bin_power_db, label=f'Bin power {wname} N={N}', linestyle='-')

plt.xlabel('Frequency (Hz)')
plt.ylabel('dB')
plt.title('PSD vs Bin Power for Different FFT Sizes and Windows')
plt.legend()
plt.grid(True)
plt.show()
