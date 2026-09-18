import pytest

from dualsense_companion.core.calibration import analyze_stick_drift


def test_stationary_offset_is_corrected_without_inflating_deadzone():
    samples = [(0.04, -0.03)] * 60

    result = analyze_stick_drift(samples)

    assert result.center_x == pytest.approx(0.04)
    assert result.center_y == pytest.approx(-0.03)
    assert result.drift_radius == pytest.approx(0.05)
    assert result.jitter_radius == pytest.approx(0.0)
    assert result.recommended_deadzone == pytest.approx(0.02)
    assert result.samples_used == 60
    assert result.rejected_samples == 0


def test_accidental_large_nudge_does_not_expand_recommended_deadzone():
    samples = [(0.035, -0.02)] * 59 + [(0.9, 0.9)]

    result = analyze_stick_drift(samples)

    assert result.center_x == pytest.approx(0.035)
    assert result.center_y == pytest.approx(-0.02)
    assert result.rejected_samples == 1
    assert result.recommended_deadzone <= 0.03


def test_residual_jitter_drives_deadzone_after_center_correction():
    samples = [(0.04 + delta, -0.03) for delta in (-0.025, -0.015, 0.0, 0.015, 0.025)] * 12

    result = analyze_stick_drift(samples)

    assert result.center_x == pytest.approx(0.04, abs=0.005)
    assert result.jitter_radius >= 0.02
    assert result.recommended_deadzone >= result.jitter_radius
    assert result.recommended_deadzone <= 0.05
