"""Bounded stick calibration and remap-only radial deadzone helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import hypot, isfinite
from statistics import median

from ..domain.models import StickCalibration, StickTelemetry


@dataclass(frozen=True, slots=True)
class CalibrationEstimate:
    center_x: float
    center_y: float
    samples_used: int
    rejected_samples: int
    noise_radius: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "center_x": self.center_x,
            "center_y": self.center_y,
            "samples_used": self.samples_used,
            "rejected_samples": self.rejected_samples,
            "noise_radius": self.noise_radius,
        }


class RobustStickCalibrator:
    """Estimate a bounded center using median/MAD noise rejection."""

    def __init__(self, *, max_samples: int = 2048, max_radius: float = 0.35) -> None:
        self.max_samples = max(8, int(max_samples))
        self.max_radius = max(0.01, min(1.0, float(max_radius)))

    def estimate(self, samples: Iterable[tuple[float, float]]) -> CalibrationEstimate:
        bounded = []
        for x, y in list(samples)[: self.max_samples]:
            candidate_x, candidate_y = float(x), float(y)
            if not isfinite(candidate_x) or not isfinite(candidate_y):
                continue
            bounded.append((max(-1.0, min(1.0, candidate_x)), max(-1.0, min(1.0, candidate_y))))
        if not bounded:
            return CalibrationEstimate(0.0, 0.0, 0, 0, 0.0)
        med_x = median(item[0] for item in bounded)
        med_y = median(item[1] for item in bounded)
        distances = [hypot(x - med_x, y - med_y) for x, y in bounded]
        med_distance = median(distances)
        deviations = [abs(value - med_distance) for value in distances]
        mad = median(deviations) if deviations else 0.0
        threshold = min(self.max_radius, max(0.01, med_distance + 3.0 * max(mad, 0.005)))
        accepted = [(x, y) for (x, y), distance in zip(bounded, distances, strict=False) if distance <= threshold]
        if not accepted:
            accepted = [(med_x, med_y)]
        center_x = max(-self.max_radius, min(self.max_radius, sum(item[0] for item in accepted) / len(accepted)))
        center_y = max(-self.max_radius, min(self.max_radius, sum(item[1] for item in accepted) / len(accepted)))
        return CalibrationEstimate(
            center_x=center_x,
            center_y=center_y,
            samples_used=len(accepted),
            rejected_samples=len(bounded) - len(accepted),
            noise_radius=threshold,
        )


def apply_radial_deadzone(
    x: float,
    y: float,
    *,
    center_x: float = 0.0,
    center_y: float = 0.0,
    deadzone: float = 0.08,
    mode: str = "native",
) -> tuple[float, float]:
    """Apply remap/exclusive deadzone only; native values are untouched."""

    if mode not in {"remap", "exclusive"}:
        return max(-1.0, min(1.0, x)), max(-1.0, min(1.0, y))
    dx = max(-1.0, min(1.0, float(x) - float(center_x)))
    dy = max(-1.0, min(1.0, float(y) - float(center_y)))
    radius = hypot(dx, dy)
    zone = max(0.0, min(0.95, float(deadzone)))
    if radius <= zone:
        return 0.0, 0.0
    scale = (radius - zone) / max(1e-9, 1.0 - zone)
    factor = scale / radius
    return max(-1.0, min(1.0, dx * factor)), max(-1.0, min(1.0, dy * factor))


def calibrated_sticks(sticks: StickTelemetry, calibration: StickCalibration, *, mode: str) -> StickTelemetry:
    left_x, left_y = apply_radial_deadzone(
        sticks.left_x,
        sticks.left_y,
        center_x=calibration.left_center_x,
        center_y=calibration.left_center_y,
        deadzone=calibration.left_deadzone,
        mode=mode,
    )
    right_x, right_y = apply_radial_deadzone(
        sticks.right_x,
        sticks.right_y,
        center_x=calibration.right_center_x,
        center_y=calibration.right_center_y,
        deadzone=calibration.right_deadzone,
        mode=mode,
    )
    return StickTelemetry(left_x, left_y, right_x, right_y)
