"""Lazy `pydualsense` USB adapter."""

from __future__ import annotations

import time
from typing import Any

from ...diagnostics.logging import get_logger
from ...domain.errors import ControllerUnavailableError, DS5ForgeError, ErrorCode, PlatformUnavailableError
from ...domain.models import (
    BatterySnapshot,
    ControllerCapabilities,
    ControllerIdentity,
    ControllerInput,
    ControllerReading,
    TouchPoint,
)

LOGGER = get_logger(__name__)


class PyDualSenseFactory:
    """Connect only through the existing wired `pydualsense` path."""

    def connect(self) -> PyDualSenseAdapter:
        try:
            from pydualsense import pydualsense  # type: ignore[import-not-found]
            from pydualsense.enums import ConnectionType  # type: ignore[import-not-found]
        except ImportError as exc:
            raise PlatformUnavailableError(
                "The pydualsense USB dependency is not installed.",
                detail=str(exc),
            ) from exc

        raw = pydualsense()
        try:
            raw.init()
        except Exception as exc:
            _close_quietly(raw)
            raise ControllerUnavailableError("DualSense USB controller is not available.", detail=str(exc)) from exc
        if getattr(raw, "conType", None) != ConnectionType.USB:
            detected = getattr(getattr(raw, "conType", None), "name", str(getattr(raw, "conType", None)))
            _close_quietly(raw)
            raise ControllerUnavailableError(
                "DS5Forge P0 accepts DualSense controllers over USB only.",
                detail=f"Detected connection type: {detected}",
            )
        return PyDualSenseAdapter(raw)


class PyDualSenseAdapter:
    def __init__(self, raw: Any) -> None:
        self.raw = raw
        self.identity = ControllerIdentity(
            model=str(getattr(raw, "model", "DualSense")),
            serial=_optional_string(getattr(raw, "serial", None)),
            vendor_id=_optional_int(getattr(raw, "vendor_id", None)),
            product_id=_optional_int(getattr(raw, "product_id", None)),
            transport="usb",
        )
        self.capabilities = ControllerCapabilities(
            usb=True,
            rumble=hasattr(raw, "setLeftMotor") and hasattr(raw, "setRightMotor"),
            touchpad=hasattr(getattr(raw, "state", None), "trackPadTouch0")
            if getattr(raw, "state", None) is not None
            else True,
            microphone_button=True,
            lightbar=hasattr(getattr(raw, "light", None), "setColorI"),
        )

    def is_connected(self) -> bool:
        return bool(getattr(self.raw, "connected", True))

    def read(self) -> ControllerReading:
        if not self.is_connected():
            return ControllerReading(connected=False)
        try:
            state = self.raw.state
            touch0 = _touch_point(getattr(state, "trackPadTouch0", None))
            touch1 = _touch_point(getattr(state, "trackPadTouch1", None))
            battery_value = getattr(getattr(self.raw, "battery", None), "Level", 0)
            return ControllerReading(
                connected=True,
                battery=BatterySnapshot(
                    level=_optional_int(battery_value) or 0,
                    charging=_optional_bool(getattr(getattr(self.raw, "battery", None), "Charging", None)),
                ),
                input=ControllerInput(
                    l3=bool(getattr(state, "L3", False)),
                    r3=bool(getattr(state, "R3", False)),
                    mic_button=bool(getattr(state, "micBtn", False)),
                    touchpad_button=bool(getattr(state, "touchBtn", False)),
                    touch0=touch0,
                    touch1=touch1,
                ),
            )
        except Exception as exc:
            raise DS5ForgeError(
                ErrorCode.CONTROLLER_READ_FAILED,
                "Controller input could not be read.",
                detail=str(exc),
            ) from exc

    def set_motors(self, left: int, right: int) -> None:
        left, right = _motor_value(left), _motor_value(right)
        try:
            self.raw.setLeftMotor(left)
            self.raw.setRightMotor(right)
        except Exception as exc:
            raise DS5ForgeError(
                ErrorCode.CONTROLLER_OUTPUT_FAILED,
                "Controller rumble output failed.",
                detail=str(exc),
            ) from exc

    def neutralize(self) -> None:
        try:
            self.set_motors(0, 0)
        except DS5ForgeError:
            LOGGER.exception("controller neutralization failed", extra={"event": "controller.neutralize"})

    def startup_feedback(self) -> None:
        """Preserve the upstream lightbar/pulse cue without changing tuning."""

        try:
            light = getattr(self.raw, "light", None)
            if light is not None and hasattr(light, "setColorI"):
                light.setColorI(0, 80, 255)
            for _ in range(2):
                self.set_motors(100, 0)
                time.sleep(0.15)
                self.set_motors(0, 0)
                time.sleep(0.1)
        except DS5ForgeError:
            LOGGER.exception("controller startup feedback failed", extra={"event": "controller.startup_feedback"})
        except Exception:
            LOGGER.exception("controller startup feedback failed", extra={"event": "controller.startup_feedback"})

    def close(self) -> None:
        try:
            self.raw.close()
        except Exception as exc:
            LOGGER.warning("controller close failed", extra={"event": "controller.close", "error": str(exc)})


def _touch_point(raw: Any) -> TouchPoint:
    if raw is None:
        return TouchPoint()
    return TouchPoint(
        active=bool(getattr(raw, "isActive", False)),
        x=float(getattr(raw, "X", 0.0)),
        y=float(getattr(raw, "Y", 0.0)),
    )


def _motor_value(value: int) -> int:
    return max(0, min(255, int(value)))


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    return bool(value) if value is not None else None


def _optional_string(value: Any) -> str | None:
    return str(value) if value is not None else None


def _close_quietly(raw: Any) -> None:
    try:
        raw.close()
    except Exception:
        LOGGER.debug("failed to close unsuccessful controller adapter", exc_info=True)
