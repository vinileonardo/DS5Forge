#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import struct
import sys
import time
import winsound
from typing import Any


def _samples(data: bytes) -> tuple[float, float]:
    if not data:
        return 0.0, 0.0
    count = len(data) // 4
    values = struct.unpack("<" + "f" * count, data[: count * 4])
    peak = max((abs(v) for v in values), default=0.0)
    rms = math.sqrt(sum(v * v for v in values) / max(1, len(values)))
    return peak, rms


def main() -> int:
    package_dir = os.path.join(sys.prefix, "Lib", "site-packages", "pydualsense")
    if os.path.isdir(package_dir):
        os.add_dll_directory(package_dir)
        os.environ["PATH"] = package_dir + os.pathsep + os.environ.get("PATH", "")

    import pyaudiowpatch as pyaudio  # type: ignore[import-not-found]

    pa = pyaudio.PyAudio()
    try:
        wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_index = int(wasapi["defaultOutputDevice"])
        default_out = pa.get_device_info_by_index(default_index)
        loopback = default_out
        candidates: list[dict[str, Any]] = []
        for candidate in pa.get_loopback_device_info_generator():
            candidates.append(
                {
                    "index": int(candidate["index"]),
                    "name": str(candidate["name"]),
                    "channels": int(candidate["maxInputChannels"]),
                    "rate": float(candidate["defaultSampleRate"]),
                }
            )
            if not default_out.get("isLoopbackDevice") and default_out["name"] in candidate["name"]:
                loopback = candidate

        rate = int(loopback["defaultSampleRate"])
        channels = max(1, int(loopback["maxInputChannels"]))
        frames = max(64, int(rate * 0.01))
        stream = pa.open(
            format=pyaudio.paFloat32,
            channels=channels,
            rate=rate,
            input=True,
            input_device_index=int(loopback["index"]),
            frames_per_buffer=frames,
        )
        try:
            baseline_peak = 0.0
            baseline_rms = 0.0
            for _ in range(30):
                peak, rms = _samples(stream.read(frames, exception_on_overflow=False))
                baseline_peak = max(baseline_peak, peak)
                baseline_rms = max(baseline_rms, rms)

            wav = r"C:\Windows\Media\Windows Notify System Generic.wav"
            if os.path.isfile(wav):
                winsound.PlaySound(wav, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)

            sound_peak = 0.0
            sound_rms = 0.0
            deadline = time.monotonic() + 2.5
            while time.monotonic() < deadline:
                peak, rms = _samples(stream.read(frames, exception_on_overflow=False))
                sound_peak = max(sound_peak, peak)
                sound_rms = max(sound_rms, rms)
        finally:
            stream.stop_stream()
            stream.close()

        print(
            json.dumps(
                {
                    "ok": True,
                    "default_output": {
                        "index": default_index,
                        "name": str(default_out["name"]),
                        "rate": float(default_out["defaultSampleRate"]),
                    },
                    "selected_loopback": {
                        "index": int(loopback["index"]),
                        "name": str(loopback["name"]),
                        "channels": channels,
                        "rate": rate,
                    },
                    "baseline": {"peak": baseline_peak, "rms": baseline_rms},
                    "system_sound": {"peak": sound_peak, "rms": sound_rms},
                    "loopback_candidates": candidates,
                },
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        pa.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
