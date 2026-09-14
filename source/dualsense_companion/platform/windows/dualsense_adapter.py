"""Lazy `pydualsense` USB adapter."""

from __future__ import annotations

import time
from typing import Any

from ...diagnostics.logging import get_logger
from ...domain.errors import (
    CapabilityUnavailableError,
    ControllerUnavailableError,
    DS5ForgeError,
    ErrorCode,
    PlatformUnavailableError,
)
from ...domain.models import (
    AdaptiveTriggerEffect,
    BatterySnapshot,
    CapabilityAvailability,
    ControllerCapabilities,
    ControllerIdentity,
    ControllerReading,
    LightbarState,
    TriggerMode,
    TriggerState,
    normalize_controller_input,
)

LOGGER = get_logger(__name__)


class PyDualSenseFactory:
    """Connect only through the existing wired `pydualsense` path."""

    def connect(self) -> PyDualSenseAdapter:
        try:
            from pydualsense import pydualsense  # type: ignore[import-not-found]
            from pydualsense.enums import ConnectionType  # type: ignore[import-not-found]

            try:
                from pydualsense import TriggerModes  # type: ignore[import-not-found]
            except ImportError:
                TriggerModes = None
            try:
                from pydualsense import Brightness, LedOptions, PulseOptions  # type: ignore[import-not-found]
            except ImportError:
                Brightness = LedOptions = PulseOptions = None
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
        return PyDualSenseAdapter(
            raw,
            trigger_modes=TriggerModes,
            brightness=Brightness,
            led_options=LedOptions,
            pulse_options=PulseOptions,
        )


class PyDualSenseAdapter:
    def __init__(
        self,
        raw: Any,
        *,
        trigger_modes: Any = None,
        brightness: Any = None,
        led_options: Any = None,
        pulse_options: Any = None,
    ) -> None:
        self.raw = raw
        self._trigger_modes = trigger_modes
        self._brightness = brightness
        self._led_options = led_options
        self._pulse_options = pulse_options
        self._lightbar_state = LightbarState()
        self._trigger_state = TriggerState()
        self.identity = ControllerIdentity(
            model=str(getattr(raw, "model", "DualSense")),
            serial=_optional_string(getattr(raw, "serial", None)),
            vendor_id=_optional_int(getattr(raw, "vendor_id", None)),
            product_id=_optional_int(getattr(raw, "product_id", None)),
            transport="usb",
        )
        light = getattr(raw, "light", None)
        trigger_left = getattr(raw, "triggerL", None)
        trigger_right = getattr(raw, "triggerR", None)
        touch_state = getattr(raw, "state", None)
        availability = {
            "usb": CapabilityAvailability(True, True),
            "rumble": _availability(
                callable(getattr(raw, "setLeftMotor", None)) and callable(getattr(raw, "setRightMotor", None)),
                "The installed adapter does not expose both motor setters.",
            ),
            "touchpad": _availability(
                touch_state is not None
                and (hasattr(touch_state, "trackPadTouch0") or hasattr(touch_state, "trackPadTouch1")),
                "The installed adapter does not expose touchpad state.",
            ),
            "microphone_button": _availability(
                touch_state is not None and hasattr(touch_state, "micBtn"),
                "The installed adapter does not expose the microphone button state.",
            ),
            "lightbar": _availability(
                callable(getattr(light, "setColorI", None)),
                "The installed adapter does not expose lightbar color output.",
            ),
            "adaptive_triggers": _availability(
                _trigger_surface_available(trigger_left, trigger_right, trigger_modes),
                "The installed adapter does not expose typed adaptive-trigger controls.",
            ),
        }
        self.capabilities = ControllerCapabilities(
            usb=True,
            rumble=availability["rumble"].enabled,
            touchpad=availability["touchpad"].enabled,
            microphone_button=availability["microphone_button"].enabled,
            lightbar=availability["lightbar"].enabled,
            adaptive_triggers=availability["adaptive_triggers"].enabled,
            availability=availability,
        )

    def is_connected(self) -> bool:
        return bool(getattr(self.raw, "connected", True))

    def read(self) -> ControllerReading:
        if not self.is_connected():
            return ControllerReading(connected=False)
        try:
            state = getattr(self.raw, "state", None)
            if state is None:
                raise DS5ForgeError(
                    ErrorCode.CONTROLLER_READ_FAILED,
                    "Controller state is unavailable.",
                )
            battery_value = getattr(getattr(self.raw, "battery", None), "Level", 0)
            return ControllerReading(
                connected=True,
                battery=BatterySnapshot(
                    level=_optional_int(battery_value) or 0,
                    charging=_optional_bool(getattr(getattr(self.raw, "battery", None), "Charging", None)),
                ),
                input=normalize_controller_input(state),
                timestamp=time.time(),
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
        try:
            self.reset_triggers()
        except DS5ForgeError:
            LOGGER.exception("trigger neutralization failed", extra={"event": "controller.trigger_neutralize"})

    def get_lightbar(self) -> LightbarState:
        capability = self.capabilities.capability("lightbar")
        if not capability.enabled:
            raise CapabilityUnavailableError("lightbar", capability.reason)
        light = getattr(self.raw, "light", None)
        color = getattr(light, "TouchpadColor", None)
        if isinstance(color, (tuple, list)) and len(color) == 3:
            try:
                return LightbarState(
                    r=int(color[0]),
                    g=int(color[1]),
                    b=int(color[2]),
                    enabled=_light_enabled(getattr(light, "ledOption", None), self._led_options),
                    brightness=_light_brightness(getattr(light, "brightness", None), self._brightness),
                    pulse=_light_pulse(getattr(light, "pulseOptions", None), self._pulse_options),
                )
            except (TypeError, ValueError):
                LOGGER.warning("controller lightbar state was malformed", extra={"event": "controller.lightbar_read"})
        return self._lightbar_state

    def set_lightbar(self, state: LightbarState) -> None:
        capability = self.capabilities.capability("lightbar")
        if not capability.enabled:
            raise CapabilityUnavailableError("lightbar", capability.reason)
        try:
            light = self.raw.light
            light.setColorI(state.r, state.g, state.b)
            if not state.enabled or (callable(getattr(light, "setLEDOption", None)) and self._led_options is not None):
                _set_light_option(light, self._led_options, "Both" if state.enabled else "Off")
            _set_light_brightness(light, self._brightness, state.brightness)
            _set_light_pulse(light, self._pulse_options, state.pulse)
            self._lightbar_state = state
        except DS5ForgeError:
            raise
        except Exception as exc:
            raise DS5ForgeError(
                ErrorCode.LIGHTBAR_OUTPUT_FAILED,
                "Lightbar output failed.",
                detail=str(exc),
            ) from exc

    def reset_lightbar(self) -> None:
        self.set_lightbar(LightbarState())

    def set_triggers(self, state: TriggerState) -> None:
        capability = self.capabilities.capability("adaptive_triggers")
        if not capability.enabled:
            raise CapabilityUnavailableError("adaptive_triggers", capability.reason)
        try:
            _set_trigger(self.raw.triggerL, state.left, self._trigger_modes)
            _set_trigger(self.raw.triggerR, state.right, self._trigger_modes)
            self._trigger_state = state
        except DS5ForgeError:
            self._reset_triggers_best_effort()
            raise
        except Exception as exc:
            self._reset_triggers_best_effort()
            raise DS5ForgeError(
                ErrorCode.TRIGGER_OUTPUT_FAILED,
                "Adaptive-trigger output failed.",
                detail=str(exc),
            ) from exc

    def set_trigger_effect(self, trigger: str, effect: AdaptiveTriggerEffect) -> None:
        current = self._trigger_state
        if trigger == "left":
            self.set_triggers(TriggerState(left=effect, right=current.right))
        elif trigger == "right":
            self.set_triggers(TriggerState(left=current.left, right=effect))
        else:
            raise DS5ForgeError(ErrorCode.API_VALIDATION, "Trigger must be left or right.")

    def reset_triggers(self) -> None:
        capability = self.capabilities.capability("adaptive_triggers")
        if not capability.enabled:
            return
        try:
            _set_trigger(self.raw.triggerL, AdaptiveTriggerEffect(), self._trigger_modes)
            _set_trigger(self.raw.triggerR, AdaptiveTriggerEffect(), self._trigger_modes)
            self._trigger_state = TriggerState()
        except Exception as exc:
            raise DS5ForgeError(
                ErrorCode.TRIGGER_OUTPUT_FAILED,
                "Adaptive triggers could not be reset.",
                detail=str(exc),
            ) from exc

    reset_trigger_effects = reset_triggers

    def _reset_triggers_best_effort(self) -> None:
        try:
            self.reset_triggers()
        except DS5ForgeError:
            LOGGER.exception("trigger reset after output failure failed", extra={"event": "controller.trigger_reset"})

    def startup_feedback(self) -> None:
        """Preserve the upstream lightbar/pulse cue without changing tuning."""

        try:
            if self.capabilities.capability("lightbar").enabled:
                self.set_lightbar(LightbarState(0, 80, 255))
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


def _availability(enabled: bool, reason: str) -> CapabilityAvailability:
    return CapabilityAvailability(supported=enabled, available=enabled, reason=None if enabled else reason)


def _trigger_surface_available(left: Any, right: Any, modes: Any) -> bool:
    return bool(
        left is not None
        and right is not None
        and callable(getattr(left, "setMode", None))
        and callable(getattr(left, "setForce", None))
        and callable(getattr(right, "setMode", None))
        and callable(getattr(right, "setForce", None))
        and modes is not None
        and getattr(modes, "Off", None) is not None
        and getattr(modes, "Rigid", None) is not None
        and _pulse_mode(modes) is not None
    )


def _trigger_mode(modes: Any, effect: AdaptiveTriggerEffect) -> Any:
    if modes is None:
        raise RuntimeError("trigger mode enum is unavailable")
    names = {
        TriggerMode.OFF.value: ("Off",),
        TriggerMode.RIGID.value: ("Rigid",),
        # pydualsense represents both resistance styles with Rigid. There is
        # no separate Resistance enum in the published adapter surface.
        TriggerMode.RESISTANCE.value: ("Rigid",),
        TriggerMode.PULSE.value: ("Pulse_AB", "PulseAB", "Pulse"),
    }
    for name in names.get(effect.mode, ("Off",)):
        candidate = getattr(modes, name, None)
        if candidate is not None:
            return candidate
    raise ValueError(f"unsupported trigger mode: {effect.mode}")


def _set_trigger(raw_trigger: Any, effect: AdaptiveTriggerEffect, modes: Any = None) -> None:
    # ``modes`` is attached by the adapter caller through the temporary
    # attribute below; keeping this helper library-agnostic makes it easy to
    # test with a small fake trigger object.
    trigger_modes = modes or getattr(raw_trigger, "_ds5forge_modes", None)
    raw_trigger.setMode(_trigger_mode(trigger_modes, effect))
    if effect.is_off:
        forces = (0, 0, 0, 0, 0, 0, 0)
    elif effect.mode in {TriggerMode.RESISTANCE.value, TriggerMode.RIGID.value}:
        # The published pydualsense examples use force slot 1 for Rigid.
        forces = (0, effect.force, 0, 0, 0, 0, 0)
    else:
        forces = (effect.start_position, effect.force, effect.end_position, effect.amplitude, effect.frequency, 0, 0)
    for index, force in enumerate(forces):
        raw_trigger.setForce(index, force)


def _reset_trigger(raw_trigger: Any, modes: Any) -> None:
    _set_trigger(raw_trigger, AdaptiveTriggerEffect(), modes)


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


def _pulse_mode(modes: Any) -> Any:
    return next(
        (
            getattr(modes, name, None)
            for name in ("Pulse_AB", "PulseAB", "Pulse")
            if getattr(modes, name, None) is not None
        ),
        None,
    )


def _set_light_option(light: Any, enum_type: Any, name: str) -> None:
    setter = getattr(light, "setLEDOption", None)
    option = getattr(enum_type, name, None) if enum_type is not None else None
    if not callable(setter) or option is None:
        raise CapabilityUnavailableError("lightbar", "The installed adapter does not expose LED enable control.")
    setter(option)


def _set_light_brightness(light: Any, enum_type: Any, value: int) -> None:
    setter = getattr(light, "setBrightness", None)
    if not callable(setter):
        if value == 2:
            return
        raise CapabilityUnavailableError("lightbar", "The installed adapter does not expose brightness control.")
    if enum_type is None and value == 2:
        return
    names = {0: "high", 1: "medium", 2: "low"}
    brightness = getattr(enum_type, names.get(value, ""), None) if enum_type is not None else None
    if brightness is None:
        raise CapabilityUnavailableError("lightbar", "The installed adapter does not expose this brightness level.")
    setter(brightness)


def _set_light_pulse(light: Any, enum_type: Any, value: str) -> None:
    setter = getattr(light, "setPulseOption", None)
    if not callable(setter):
        if value == "off":
            return
        raise CapabilityUnavailableError("lightbar", "The installed adapter does not expose pulse control.")
    if enum_type is None and value == "off":
        return
    names = {"off": "Off", "slow": "FadeBlue", "fast": "FadeOut"}
    pulse = getattr(enum_type, names.get(value, ""), None) if enum_type is not None else None
    if pulse is None:
        raise CapabilityUnavailableError("lightbar", "The installed adapter does not expose this pulse mode.")
    setter(pulse)


def _light_enabled(value: Any, enum_type: Any) -> bool:
    off = getattr(enum_type, "Off", None) if enum_type is not None else None
    return value != off if off is not None and value is not None else True


def _light_brightness(value: Any, enum_type: Any) -> int:
    raw = getattr(value, "value", value)
    if isinstance(raw, int):
        return max(0, min(2, raw))
    for number, name in ((0, "high"), (1, "medium"), (2, "low")):
        if value == getattr(enum_type, name, object()):
            return number
    return 2


def _light_pulse(value: Any, enum_type: Any) -> str:
    for name, label in (("Off", "off"), ("FadeBlue", "slow"), ("FadeOut", "fast")):
        if value == getattr(enum_type, name, object()):
            return label
    return "off"


def _close_quietly(raw: Any) -> None:
    try:
        raw.close()
    except Exception:
        LOGGER.debug("failed to close unsuccessful controller adapter", exc_info=True)
