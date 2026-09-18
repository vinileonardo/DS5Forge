#!/usr/bin/env python3
from __future__ import annotations

import math
import struct

import pyaudiowpatch as pyaudio  # type: ignore[import-not-found]

RATE = 48_000
FREQ = 100.0
SECONDS = 1.2
AMPLITUDE = 0.18

pa = pyaudio.PyAudio()
try:
    wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
    index = int(wasapi["defaultOutputDevice"])
    info = pa.get_device_info_by_index(index)
    channels = max(1, int(info["maxOutputChannels"]))
    rate = int(info["defaultSampleRate"])
    stream = pa.open(
        format=pyaudio.paFloat32,
        channels=channels,
        rate=rate,
        output=True,
        output_device_index=index,
        frames_per_buffer=480,
    )
    try:
        total = int(rate * SECONDS)
        phase = 0
        chunk = 480
        while phase < total:
            count = min(chunk, total - phase)
            frames = []
            for i in range(count):
                sample = AMPLITUDE * math.sin(2.0 * math.pi * FREQ * (phase + i) / rate)
                frames.extend([sample] * channels)
            stream.write(struct.pack("<" + "f" * len(frames), *frames))
            phase += count
    finally:
        stream.stop_stream()
        stream.close()
finally:
    pa.terminate()
