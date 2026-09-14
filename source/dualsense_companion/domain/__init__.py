"""Stable, platform-neutral contracts used by DS5Forge."""

from .errors import (
    ConfigValidationError,
    ControllerUnavailableError,
    DS5ForgeError,
    ErrorCode,
    PlatformUnavailableError,
)
from .events import EventEnvelope, EventType
from .models import (
    AudioSnapshot,
    BatterySnapshot,
    ConnectionState,
    ControllerCapabilities,
    ControllerIdentity,
    ControllerInput,
    ControllerReading,
    ErrorSnapshot,
    HealthSnapshot,
    MotorSnapshot,
    RuntimeSnapshot,
    TouchPoint,
)

__all__ = [
    "AudioSnapshot",
    "BatterySnapshot",
    "ConfigValidationError",
    "ConnectionState",
    "ControllerCapabilities",
    "ControllerIdentity",
    "ControllerInput",
    "ControllerReading",
    "ControllerUnavailableError",
    "DS5ForgeError",
    "ErrorCode",
    "ErrorSnapshot",
    "EventEnvelope",
    "EventType",
    "HealthSnapshot",
    "MotorSnapshot",
    "PlatformUnavailableError",
    "RuntimeSnapshot",
    "TouchPoint",
]
