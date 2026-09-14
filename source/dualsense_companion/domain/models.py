"""Immutable domain snapshots and controller input contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from enum import StrEnum
from math import isfinite
from types import MappingProxyType
from typing import Any

from .errors import ErrorCode


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


@dataclass(frozen=True, slots=True)
class BatterySnapshot:
    level: int = 0
    charging: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "level", max(0, min(100, int(self.level))))


@dataclass(frozen=True, slots=True)
class MotorSnapshot:
    left: int = 0
    right: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "left", max(0, min(255, int(self.left))))
        object.__setattr__(self, "right", max(0, min(255, int(self.right))))


@dataclass(frozen=True, slots=True)
class AudioSnapshot:
    status: str = "stopped"
    device: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    process_alive: bool = True
    controller_available: bool = False
    subsystems: Mapping[str, str] = field(default_factory=dict)
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
    fields: Mapping[str, Any] = field(default_factory=dict)

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


@dataclass(frozen=True, slots=True)
class ControllerInput:
    l3: bool = False
    r3: bool = False
    mic_button: bool = False
    touchpad_button: bool = False
    touch0: TouchPoint = field(default_factory=TouchPoint)
    touch1: TouchPoint = field(default_factory=TouchPoint)


@dataclass(frozen=True, slots=True)
class ControllerReading:
    connected: bool = True
    battery: BatterySnapshot = field(default_factory=BatterySnapshot)
    input: ControllerInput = field(default_factory=ControllerInput)


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    connection: ConnectionState = ConnectionState.DISCONNECTED
    identity: ControllerIdentity | None = None
    capabilities: ControllerCapabilities = field(default_factory=ControllerCapabilities)
    battery: BatterySnapshot = field(default_factory=BatterySnapshot)
    motors: MotorSnapshot = field(default_factory=MotorSnapshot)
    rumble_enabled: bool = True
    touchpad_enabled: bool = True
    active_profile: str = "Default"
    config_version: int = 1
    audio: AudioSnapshot = field(default_factory=AudioSnapshot)
    last_error: ErrorSnapshot | None = None
    health: HealthSnapshot = field(default_factory=HealthSnapshot)
    sequence: int = 0
    updated_at: float = 0.0

    @classmethod
    def initial(cls, *, touchpad_enabled: bool = True, now: float = 0.0) -> RuntimeSnapshot:
        return cls(touchpad_enabled=touchpad_enabled, updated_at=now)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


def _jsonable(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
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
