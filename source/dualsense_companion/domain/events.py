"""Versioned events shared by HTTP/WebSocket clients and the legacy UI."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    STATE_SNAPSHOT = "state.snapshot"
    STATE_UPDATED = "state.updated"
    LIFECYCLE = "controller.lifecycle"
    AUDIO = "audio.status"
    PROFILE = "profile.changed"
    CONFIG = "config.changed"
    DIAGNOSTIC = "diagnostic"


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """Wire contract: every event has a type, version and JSON payload."""

    type: str
    payload: Mapping[str, Any]
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "version": self.version,
            "payload": _jsonable(self.payload),
        }


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, StrEnum):
        return value.value
    return value
