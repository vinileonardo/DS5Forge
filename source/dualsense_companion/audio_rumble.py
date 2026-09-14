"""Compatibility exports for the upstream module name.

The implementation now lives in ``core.dsp`` and ``core.haptics_service``;
this module remains so downstream code importing the baseline symbols does not
break during P0.
"""

from __future__ import annotations

import threading
from typing import Any

from .core.dsp import Biquad, EnvelopeFollower, map_rumble_level
from .core.haptics_service import HapticsService
from .diagnostics.logging import get_logger
from .platform.windows.audio_capture import WasapiLoopbackFactory

LOGGER = get_logger(__name__)


class _LegacyMotorOutput:
    def __init__(self, state: Any) -> None:
        self.facade = getattr(state, "facade", None)

    def __call__(self, left: int, right: int) -> bool:
        if self.facade is None:
            return False
        try:
            return bool(self.facade.controller.set_motors(left, right))
        except Exception:
            LOGGER.exception("legacy motor output failed", extra={"event": "audio.legacy_motor_output"})
            return False


class AudioRumbleEngine(HapticsService):
    """Upstream-compatible constructor backed by the new service."""

    def __init__(self, state: Any) -> None:
        facade = getattr(state, "facade", None)
        if facade is None:
            raise TypeError("AudioRumbleEngine now requires a CoreFacade-backed state")
        reload_event = getattr(facade, "_reload_audio", None) or threading.Event()
        super().__init__(
            _LegacyMotorOutput(state),
            lambda: facade.config()["rumble"],
            lambda: bool(facade.snapshot().rumble_enabled),
            capture_factory=WasapiLoopbackFactory(),
            reload_event=reload_event,
        )

    def _map(self, level: float, transient: float, config: dict[str, Any], texture: bool = False) -> int:
        """Keep the upstream private helper available to existing tests."""

        return map_rumble_level(level, transient, config, texture=texture)


__all__ = ["AudioRumbleEngine", "Biquad", "EnvelopeFollower", "map_rumble_level"]
