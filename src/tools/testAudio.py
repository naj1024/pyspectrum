import queue
import time

import sounddevice as sd
import numpy as np

deviceA = 0
audio_q = queue.Queue(3)


def callback_s(samples, frames, time_1, status):
    if status:
        if status.input_overflow:
            print("audio input overflow")
        else:
            raise ValueError("Problem with audio callback")

    cplx_data = np.zeros(shape=(frames,), dtype=np.complex64)

    if samples.shape[1] >= 2:
        for n in range(frames):
            cplx_data[n] = complex(samples[n][0], samples[n][1])
    else:
        for n in range(frames):
            cplx_data[n] = complex(samples[n], samples[n])

    try:
        audio_q.put(cplx_data.copy())
    except queue.Full:
        print("not emptying queue fast enough")
        pass


print(sd.query_devices())
print("")
dev = sd.query_devices(device=deviceA)
print(dev)
print("")

num_channels = 2
if dev['max_input_channels'] < 2:
    num_channels = 1
print(f"Using {num_channels} channels")

inq = sd.InputStream(device=deviceA, samplerate=48000, channels=num_channels,
                     callback=callback_s, blocksize=2048, dtype="float32")
inq.start()

empty = 0
count = 0
while True:
    try:
        cp = audio_q.get(block=False)
        count += 1
        print(f"{count}")
    except queue.Empty:
        time.sleep(0.001)
        empty += 1
        if empty > 3000:
            empty = 0
            print("not getting audio samples")
        pass
