"""Pure audio DSP retained from the upstream haptics tuning.

This module intentionally has no NumPy, WASAPI or controller imports. It is
usable in Linux CI and by deterministic unit tests while the Windows capture
adapter remains replaceable.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any

from ..domain.models import finite_number


class Biquad:
    def __init__(self, b0: float, b1: float, b2: float, a1: float, a2: float) -> None:
        values = (b0, b1, b2, a1, a2)
        if not all(finite_number(value) for value in values):
            raise ValueError("biquad coefficients must be finite numbers")
        self.b0, self.b1, self.b2 = map(float, (b0, b1, b2))
        self.a1, self.a2 = map(float, (a1, a2))
        self.x1 = self.x2 = self.y1 = self.y2 = 0.0

    @classmethod
    def lowpass(cls, fs: float, fc: float, q: float = 0.707) -> Biquad:
        _validate_filter_args(fs, fc, q)
        w0 = 2 * math.pi * fc / fs
        alpha = math.sin(w0) / (2 * q)
        cosw = math.cos(w0)
        a0 = 1 + alpha
        return cls(
            (1 - cosw) / 2 / a0,
            (1 - cosw) / a0,
            (1 - cosw) / 2 / a0,
            (-2 * cosw) / a0,
            (1 - alpha) / a0,
        )

    @classmethod
    def bandpass(cls, fs: float, fc: float, q: float = 0.9) -> Biquad:
        _validate_filter_args(fs, fc, q)
        w0 = 2 * math.pi * fc / fs
        alpha = math.sin(w0) / (2 * q)
        cosw = math.cos(w0)
        a0 = 1 + alpha
        return cls(alpha / a0, 0.0, -alpha / a0, (-2 * cosw) / a0, (1 - alpha) / a0)

    def process(self, samples: Sequence[float] | Iterable[float]) -> list[float]:
        output: list[float] = []
        x1, x2, y1, y2 = self.x1, self.x2, self.y1, self.y2
        for sample in samples:
            xi = float(sample)
            yi = self.b0 * xi + self.b1 * x1 + self.b2 * x2 - self.a1 * y1 - self.a2 * y2
            x2, x1 = x1, xi
            y2, y1 = y1, yi
            output.append(yi)
        self.x1, self.x2, self.y1, self.y2 = x1, x2, y1, y2
        return output


class EnvelopeFollower:
    def __init__(self, attack_ms: float, release_ms: float, chunk_ms: float) -> None:
        if not all(finite_number(value) for value in (attack_ms, release_ms, chunk_ms)):
            raise ValueError("envelope timings must be finite numbers")
        if min(float(attack_ms), float(release_ms), float(chunk_ms)) <= 0:
            raise ValueError("envelope timings must be positive")
        self.attack = math.exp(-chunk_ms / max(attack_ms, 1e-3))
        self.release = math.exp(-chunk_ms / max(release_ms, 1e-3))
        self.value = 0.0

    def update(self, peak: float) -> float:
        peak = max(0.0, float(peak))
        coef = self.attack if peak > self.value else self.release
        self.value = coef * self.value + (1 - coef) * peak
        return self.value


def map_rumble_level(level: float, transient: float, config: dict[str, Any], *, texture: bool = False) -> int:
    """Map filtered signal levels to the upstream 0-255 motor range."""

    gate = float(config["gate"]) * (float(config["texture_gate_mult"]) if texture else 1.0)
    span = max(float(config["impact_level"]) - gate, 1e-6)
    normalized = min(1.0, max(0.0, (float(level) - gate) / span)) ** float(config["gamma"])
    transient_term = 0.0
    if level >= config["transient_min_level"] and transient > 0:
        transient_term = min(
            1.0,
            (float(transient) * float(config["transient_gain"])) / max(float(config["impact_level"]), 1e-6),
        )
    drive = min(1.0, normalized + float(config["transient_weight"]) * transient_term)
    if drive < float(config["drive_gate"]):
        return 0
    floor = 0.0 if texture else float(config["min_rumble"])
    value = floor + drive * (float(config["max_rumble"]) - floor)
    return max(0, min(255, int(round(value))))


def _validate_filter_args(fs: float, fc: float, q: float) -> None:
    if not all(finite_number(value) for value in (fs, fc, q)):
        raise ValueError("filter arguments must be finite numbers")
    if fs <= 0 or fc <= 0 or fc >= fs / 2 or q <= 0:
        raise ValueError("filter requires 0 < cutoff < Nyquist and q > 0")


def pcm_float32(data: bytes, channels: int) -> list[float]:
    """Decode interleaved float32 PCM without making NumPy mandatory."""

    import struct

    if channels < 1 or len(data) % 4:
        return []
    count = len(data) // 4
    values = struct.unpack("<" + "f" * count, data)
    if channels == 1:
        return list(values)
    frames = count // channels
    return [sum(values[i * channels : (i + 1) * channels]) / channels for i in range(frames)]


def validate_dsp_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate the numerical safety boundary before a value reaches DSP."""

    from .config import validate_config

    return validate_config({"rumble": config})["rumble"]
