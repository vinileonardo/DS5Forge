"""Immutable domain snapshots and Controller Lab contracts.

The domain module deliberately contains no Windows or controller-library
imports.  Platform adapters normalize their objects into these immutable
values before the rest of the application can observe them.
"""

from __future__ import annotations

from collections.abc import Mapping as ABCMapping
from dataclasses import dataclass, field, fields, is_dataclass
from enum import StrEnum
from math import isfinite
from types import MappingProxyType
from typing import Any, ClassVar

from .errors import ErrorCode
from .games import (
    AutomationState,
    CompatibilityState,
    ConflictDiagnostic,
    ForegroundApplication,
    SyntheticOutputState,
)


class ConnectionState(StrEnum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"
    STOPPING = "stopping"


@dataclass(frozen=True, slots=True)
class ControllerIdentity:
    model: str = "DualSense"
    serial: str | None = None
    vendor_id: int | None = None
    product_id: int | None = None
    transport: str = "usb"


@dataclass(frozen=True, slots=True)
class ControllerCapabilities:
    usb: bool = True
    rumble: bool = True
    touchpad: bool = True
    microphone_button: bool = True
    lightbar: bool = True
    adaptive_triggers: bool = False
    availability: ABCMapping[str, CapabilityAvailability] = field(default_factory=dict)

    _NAMES: ClassVar[tuple[str, ...]] = (
        "usb",
        "rumble",
        "touchpad",
        "microphone_button",
        "lightbar",
        "adaptive_triggers",
    )

    def __post_init__(self) -> None:
        values = {
            "usb": self.usb,
            "rumble": self.rumble,
            "touchpad": self.touchpad,
            "microphone_button": self.microphone_button,
            "lightbar": self.lightbar,
            "adaptive_triggers": self.adaptive_triggers,
        }
        supplied = dict(self.availability)
        normalized = {
            name: supplied.get(
                name,
                CapabilityAvailability(
                    supported=bool(values[name]),
                    available=bool(values[name]),
                    reason=None if values[name] else "The connected adapter does not expose this capability.",
                ),
            )
            for name in self._NAMES
        }
        object.__setattr__(self, "availability", MappingProxyType(normalized))

    def capability(self, name: str) -> CapabilityAvailability:
        if name not in self._NAMES:
            raise KeyError(name)
        return self.availability[name]

    @classmethod
    def unavailable(cls, reason: str = "No connected USB controller is available.") -> ControllerCapabilities:
        availability = {
            name: CapabilityAvailability(supported=False, available=False, reason=reason) for name in cls._NAMES
        }
        return cls(
            usb=False,
            rumble=False,
            touchpad=False,
            microphone_button=False,
            lightbar=False,
            adaptive_triggers=False,
            availability=availability,
        )


@dataclass(frozen=True, slots=True)
class CapabilityAvailability:
    """Availability and safe explanation for one hardware-dependent feature."""

    supported: bool
    available: bool
    reason: str | None = None

    @property
    def enabled(self) -> bool:
        return self.supported and self.available


@dataclass(frozen=True, slots=True)
class BatterySnapshot:
    level: int = 0
    charging: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "level", max(0, min(100, _safe_int(self.level, 0))))


@dataclass(frozen=True, slots=True)
class MotorSnapshot:
    left: int = 0
    right: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "left", max(0, min(255, _safe_int(self.left, 0))))
        object.__setattr__(self, "right", max(0, min(255, _safe_int(self.right, 0))))


@dataclass(frozen=True, slots=True)
class AudioSnapshot:
    status: str = "stopped"
    device: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    process_alive: bool = True
    controller_available: bool = False
    subsystems: ABCMapping[str, str] = field(default_factory=dict)
    degraded: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "subsystems", MappingProxyType(dict(self.subsystems)))
        object.__setattr__(self, "degraded", tuple(self.degraded))

    @property
    def status(self) -> str:
        if not self.process_alive:
            return "stopped"
        if self.degraded:
            return "degraded"
        if not self.controller_available:
            return "waiting_for_controller"
        return "healthy"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "process_alive": self.process_alive,
            "controller_available": self.controller_available,
            "subsystems": dict(self.subsystems),
            "degraded": list(self.degraded),
        }


@dataclass(frozen=True, slots=True)
class ErrorSnapshot:
    code: ErrorCode | str
    message: str
    detail: str | None = None
    recoverable: bool = True
    fields: ABCMapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value if isinstance(self.code, StrEnum) else self.code,
            "message": self.message,
            "detail": self.detail,
            "recoverable": self.recoverable,
            "fields": dict(self.fields),
        }


@dataclass(frozen=True, slots=True)
class TouchPoint:
    active: bool = False
    x: float = 0.0
    y: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "active", bool(self.active))
        object.__setattr__(self, "x", _finite_or_zero(self.x))
        object.__setattr__(self, "y", _finite_or_zero(self.y))


@dataclass(frozen=True, slots=True)
class StickTelemetry:
    """Normalized stick positions in the range -1..1."""

    left_x: float = 0.0
    left_y: float = 0.0
    right_x: float = 0.0
    right_y: float = 0.0

    def __post_init__(self) -> None:
        for name in ("left_x", "left_y", "right_x", "right_y"):
            object.__setattr__(self, name, _clamp_unit(getattr(self, name)))


@dataclass(frozen=True, slots=True)
class ControllerInput:
    """Complete normalized digital and analog input projection.

    Trigger values are normalized to 0..1 and stick values to -1..1.  The
    explicit fields keep the wire contract easy for clients to render while
    ``sticks`` provides a stable grouped projection for newer clients.
    """

    square: bool = False
    triangle: bool = False
    circle: bool = False
    cross: bool = False
    dpad_up: bool = False
    dpad_down: bool = False
    dpad_left: bool = False
    dpad_right: bool = False
    l1: bool = False
    r1: bool = False
    l2_button: bool = False
    r2_button: bool = False
    l3: bool = False
    r3: bool = False
    options: bool = False
    share: bool = False
    ps: bool = False
    mic_button: bool = False
    touchpad_button: bool = False
    l2: float = 0.0
    r2: float = 0.0
    sticks: StickTelemetry = field(default_factory=StickTelemetry)
    touch0: TouchPoint = field(default_factory=TouchPoint)
    touch1: TouchPoint = field(default_factory=TouchPoint)

    def __post_init__(self) -> None:
        for name in (
            "square",
            "triangle",
            "circle",
            "cross",
            "dpad_up",
            "dpad_down",
            "dpad_left",
            "dpad_right",
            "l1",
            "r1",
            "l2_button",
            "r2_button",
            "l3",
            "r3",
            "options",
            "share",
            "ps",
            "mic_button",
            "touchpad_button",
        ):
            object.__setattr__(self, name, bool(getattr(self, name)))
        object.__setattr__(self, "l2", _clamp_zero_one(self.l2))
        object.__setattr__(self, "r2", _clamp_zero_one(self.r2))
        if not isinstance(self.sticks, StickTelemetry):
            object.__setattr__(self, "sticks", StickTelemetry())

    # Compatibility aliases make the domain pleasant for callers that use
    # the library's source field names without leaking those names to clients.
    @property
    def left_stick_x(self) -> float:
        return self.sticks.left_x

    @property
    def left_stick_y(self) -> float:
        return self.sticks.left_y

    @property
    def right_stick_x(self) -> float:
        return self.sticks.right_x

    @property
    def right_stick_y(self) -> float:
        return self.sticks.right_y

    @property
    def buttons(self) -> ABCMapping[str, bool]:
        return MappingProxyType(
            {
                "square": self.square,
                "triangle": self.triangle,
                "circle": self.circle,
                "cross": self.cross,
                "dpad_up": self.dpad_up,
                "dpad_down": self.dpad_down,
                "dpad_left": self.dpad_left,
                "dpad_right": self.dpad_right,
                "l1": self.l1,
                "r1": self.r1,
                "l2": self.l2_button,
                "r2": self.r2_button,
                "l3": self.l3,
                "r3": self.r3,
                "options": self.options,
                "share": self.share,
                "ps": self.ps,
                "mic_button": self.mic_button,
                "touchpad_button": self.touchpad_button,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "square": self.square,
            "triangle": self.triangle,
            "circle": self.circle,
            "cross": self.cross,
            "dpad_up": self.dpad_up,
            "dpad_down": self.dpad_down,
            "dpad_left": self.dpad_left,
            "dpad_right": self.dpad_right,
            "l1": self.l1,
            "r1": self.r1,
            "l2_button": self.l2_button,
            "r2_button": self.r2_button,
            "l3": self.l3,
            "r3": self.r3,
            "options": self.options,
            "share": self.share,
            "ps": self.ps,
            "mic_button": self.mic_button,
            "touchpad_button": self.touchpad_button,
            "l2": self.l2,
            "r2": self.r2,
            "sticks": _jsonable(self.sticks),
            "touch0": _jsonable(self.touch0),
            "touch1": _jsonable(self.touch1),
            "buttons": dict(self.buttons),
        }


@dataclass(frozen=True, slots=True)
class ControllerTelemetry:
    input: ControllerInput = field(default_factory=ControllerInput)
    sequence: int = 0
    timestamp: float = 0.0
    sample_rate_hz: float = 30.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", max(0, int(self.sequence)))
        object.__setattr__(self, "timestamp", _finite_or_zero(self.timestamp))
        object.__setattr__(self, "sample_rate_hz", max(0.0, _finite_or_zero(self.sample_rate_hz)))

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class LightbarState:
    r: int = 0
    g: int = 0
    b: int = 0
    enabled: bool = True
    brightness: int = 2
    pulse: str = "off"

    def __post_init__(self) -> None:
        for name in ("r", "g", "b"):
            object.__setattr__(self, name, max(0, min(255, int(getattr(self, name)))))
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "brightness", max(0, min(2, int(self.brightness))))
        object.__setattr__(self, "pulse", str(self.pulse))

    @property
    def red(self) -> int:
        return self.r

    @property
    def green(self) -> int:
        return self.g

    @property
    def blue(self) -> int:
        return self.b

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


class TriggerMode(StrEnum):
    OFF = "off"
    RESISTANCE = "resistance"
    PULSE = "pulse"
    RIGID = "rigid"


@dataclass(frozen=True, slots=True)
class AdaptiveTriggerEffect:
    mode: str = TriggerMode.OFF.value
    start_position: int = 0
    end_position: int = 255
    force: int = 0
    frequency: int = 0
    amplitude: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", str(self.mode).lower())
        for name in ("start_position", "end_position", "force", "frequency", "amplitude"):
            object.__setattr__(self, name, max(0, min(255, int(getattr(self, name)))))

    @property
    def is_off(self) -> bool:
        return self.mode == TriggerMode.OFF.value

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class TriggerState:
    left: AdaptiveTriggerEffect = field(default_factory=AdaptiveTriggerEffect)
    right: AdaptiveTriggerEffect = field(default_factory=AdaptiveTriggerEffect)
    preview: TriggerPreviewState | None = None

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class TriggerPreviewState:
    id: str
    status: str
    started_at: float
    expires_at: float
    error: ErrorSnapshot | None = None

    @property
    def active(self) -> bool:
        return self.status == "running"

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class HapticsTestRun:
    id: str
    status: str
    left: int
    right: int
    duration_ms: int
    started_at: float
    expires_at: float
    error: ErrorSnapshot | None = None

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class StickCalibration:
    left_deadzone: float = 0.08
    right_deadzone: float = 0.08
    left_center_x: float = 0.0
    left_center_y: float = 0.0
    right_center_x: float = 0.0
    right_center_y: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "left_deadzone", _clamp_zero_one(self.left_deadzone))
        object.__setattr__(self, "right_deadzone", _clamp_zero_one(self.right_deadzone))
        for name in ("left_center_x", "left_center_y", "right_center_x", "right_center_y"):
            object.__setattr__(self, name, _clamp_unit(getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class GestureConfig:
    enabled: bool = True
    two_finger_scroll: bool = True
    tap_to_click: bool = True
    swipe_enabled: bool = True
    swipe_threshold: float = 40.0

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class ControllerProfile:
    """Schema-v2 full profile, serialized as plain JSON by the repository."""

    name: str
    schema_version: int = 2
    rumble: ABCMapping[str, Any] = field(default_factory=dict)
    lightbar: LightbarState = field(default_factory=LightbarState)
    triggers: TriggerState = field(default_factory=TriggerState)
    sticks: StickCalibration = field(default_factory=StickCalibration)
    touchpad: GestureConfig = field(default_factory=GestureConfig)
    unsupported_sections: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "rumble", MappingProxyType(dict(self.rumble)))
        object.__setattr__(self, "unsupported_sections", tuple(self.unsupported_sections))


@dataclass(frozen=True, slots=True)
class ControllerReading:
    connected: bool = True
    battery: BatterySnapshot = field(default_factory=BatterySnapshot)
    input: ControllerInput = field(default_factory=ControllerInput)
    timestamp: float = 0.0


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    connection: ConnectionState = ConnectionState.DISCONNECTED
    identity: ControllerIdentity | None = None
    capabilities: ControllerCapabilities = field(default_factory=ControllerCapabilities.unavailable)
    battery: BatterySnapshot = field(default_factory=BatterySnapshot)
    motors: MotorSnapshot = field(default_factory=MotorSnapshot)
    input: ControllerInput = field(default_factory=ControllerInput)
    telemetry: ControllerTelemetry = field(default_factory=ControllerTelemetry)
    lightbar: LightbarState = field(default_factory=LightbarState)
    triggers: TriggerState = field(default_factory=TriggerState)
    haptics_test: HapticsTestRun | None = None
    stick_calibration: StickCalibration = field(default_factory=StickCalibration)
    gesture_config: GestureConfig = field(default_factory=GestureConfig)
    rumble_enabled: bool = True
    touchpad_enabled: bool = True
    active_profile: str = "Default"
    config_version: int = 1
    audio: AudioSnapshot = field(default_factory=AudioSnapshot)
    last_error: ErrorSnapshot | None = None
    health: HealthSnapshot = field(default_factory=HealthSnapshot)
    sequence: int = 0
    updated_at: float = 0.0
    foreground: ForegroundApplication = field(default_factory=ForegroundApplication)
    automation: AutomationState = field(default_factory=AutomationState)
    compatibility: CompatibilityState = field(default_factory=CompatibilityState)
    synthetic_outputs: SyntheticOutputState = field(default_factory=SyntheticOutputState)
    conflicts: tuple[ConflictDiagnostic, ...] = ()

    @classmethod
    def initial(cls, *, touchpad_enabled: bool = True, now: float = 0.0) -> RuntimeSnapshot:
        return cls(touchpad_enabled=touchpad_enabled, updated_at=now)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


def _jsonable(value: Any) -> Any:
    if isinstance(value, ControllerInput):
        return value.to_dict()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, ABCMapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if is_dataclass(value):
        return {item.name: _jsonable(getattr(value, item.name)) for item in fields(value)}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value


def finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(float(value))


def _finite_or_zero(value: Any) -> float:
    return float(value) if finite_number(value) else 0.0


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value) if value is not None and not isinstance(value, bool) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _clamp_unit(value: Any) -> float:
    return max(-1.0, min(1.0, _finite_or_zero(value)))


def _clamp_zero_one(value: Any) -> float:
    return max(0.0, min(1.0, _finite_or_zero(value)))


def _read_value(value: Any, *names: str, default: Any = None) -> Any:
    if isinstance(value, ABCMapping):
        for name in names:
            if name in value:
                return value[name]
        return default
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _normalize_axis(value: Any, *, raw_min: float = 0.0, raw_max: float = 255.0) -> float:
    if not finite_number(value):
        return 0.0
    numeric = float(value)
    if -1.0 <= numeric <= 1.0:
        return numeric
    return max(-1.0, min(1.0, ((numeric - raw_min) / (raw_max - raw_min)) * 2.0 - 1.0))


def _normalize_signed_axis(value: Any) -> float:
    """Normalize the adapter's signed -128..127 stick fields."""

    if not finite_number(value):
        return 0.0
    return max(-1.0, min(1.0, float(value) / 127.0))


def _normalize_trigger(value: Any) -> float:
    if not finite_number(value):
        return 0.0
    numeric = float(value)
    if numeric > 1.0:
        numeric /= 255.0
    return _clamp_zero_one(numeric)


def _normalize_raw_trigger(value: Any) -> float:
    if not finite_number(value):
        return 0.0
    return _clamp_zero_one(float(value) / 255.0)


def _axis_value(value: Any, nested: Any, *, normalized_names: tuple[str, ...], signed_names: tuple[str, ...]) -> float:
    normalized = _read_value(value, *normalized_names, default=None)
    if normalized is not None:
        return _normalize_axis(normalized)
    nested_value = _read_value(nested, *normalized_names, default=None)
    if nested_value is not None:
        return _normalize_axis(nested_value)
    signed = _read_value(value, *signed_names, default=None)
    return _normalize_signed_axis(signed)


def _trigger_value(value: Any, *, normalized_names: tuple[str, ...], raw_names: tuple[str, ...]) -> float:
    normalized = _read_value(value, *normalized_names, default=None)
    if normalized is not None:
        return _normalize_trigger(normalized)
    return _normalize_raw_trigger(_read_value(value, *raw_names, default=None))


def _normalize_touch(value: Any) -> TouchPoint:
    if isinstance(value, TouchPoint):
        return value
    if value is None:
        return TouchPoint()
    return TouchPoint(
        active=bool(_read_value(value, "active", "isActive", default=False)),
        x=_finite_or_zero(_read_value(value, "x", "X", default=0.0)),
        y=_finite_or_zero(_read_value(value, "y", "Y", default=0.0)),
    )


def normalize_controller_input(value: Any) -> ControllerInput:
    """Normalize a mapping or adapter state object into a complete input value."""

    if isinstance(value, ControllerInput):
        return value
    nested_sticks = _read_value(value, "sticks", default=None)
    sticks = StickTelemetry(
        left_x=_axis_value(
            value,
            nested_sticks,
            normalized_names=("left_stick_x", "stick_left_x", "left_x"),
            signed_names=("LX",),
        ),
        left_y=_axis_value(
            value,
            nested_sticks,
            normalized_names=("left_stick_y", "stick_left_y", "left_y"),
            signed_names=("LY",),
        ),
        right_x=_axis_value(
            value,
            nested_sticks,
            normalized_names=("right_stick_x", "stick_right_x", "right_x"),
            signed_names=("RX",),
        ),
        right_y=_axis_value(
            value,
            nested_sticks,
            normalized_names=("right_stick_y", "stick_right_y", "right_y"),
            signed_names=("RY",),
        ),
    )
    return ControllerInput(
        square=bool(_read_value(value, "square", default=False)),
        triangle=bool(_read_value(value, "triangle", default=False)),
        circle=bool(_read_value(value, "circle", default=False)),
        cross=bool(_read_value(value, "cross", default=False)),
        dpad_up=bool(_read_value(value, "dpad_up", "DpadUp", default=False)),
        dpad_down=bool(_read_value(value, "dpad_down", "DpadDown", default=False)),
        dpad_left=bool(_read_value(value, "dpad_left", "DpadLeft", default=False)),
        dpad_right=bool(_read_value(value, "dpad_right", "DpadRight", default=False)),
        l1=bool(_read_value(value, "l1", "L1", default=False)),
        r1=bool(_read_value(value, "r1", "R1", default=False)),
        l2_button=bool(_read_value(value, "l2_button", "L2Btn", "L2", default=False)),
        r2_button=bool(_read_value(value, "r2_button", "R2Btn", "R2", default=False)),
        l3=bool(_read_value(value, "l3", "L3", default=False)),
        r3=bool(_read_value(value, "r3", "R3", default=False)),
        options=bool(_read_value(value, "options", "Option", default=False)),
        share=bool(_read_value(value, "share", "Share", default=False)),
        ps=bool(_read_value(value, "ps", "PS", default=False)),
        mic_button=bool(_read_value(value, "mic_button", "micBtn", default=False)),
        touchpad_button=bool(_read_value(value, "touchpad_button", "touchBtn", default=False)),
        l2=_trigger_value(value, normalized_names=("l2",), raw_names=("l2_value", "L2_value")),
        r2=_trigger_value(value, normalized_names=("r2",), raw_names=("r2_value", "R2_value")),
        sticks=sticks,
        touch0=_normalize_touch(_read_value(value, "touch0", "trackPadTouch0", default=None)),
        touch1=_normalize_touch(_read_value(value, "touch1", "trackPadTouch1", default=None)),
    )


def normalize_controller_reading(value: Any) -> ControllerReading:
    if isinstance(value, ControllerReading):
        return value
    battery_value = _read_value(value, "battery", default=None)
    battery = (
        battery_value
        if isinstance(battery_value, BatterySnapshot)
        else BatterySnapshot(
            level=_safe_int(_read_value(battery_value, "level", "Level", default=0), 0),
            charging=_read_value(battery_value, "charging", "Charging", default=None),
        )
    )
    raw_input = _read_value(value, "input", "state", default=value)
    return ControllerReading(
        connected=bool(_read_value(value, "connected", default=True)),
        battery=battery,
        input=normalize_controller_input(raw_input),
        timestamp=_finite_or_zero(_read_value(value, "timestamp", default=0.0)),
    )
