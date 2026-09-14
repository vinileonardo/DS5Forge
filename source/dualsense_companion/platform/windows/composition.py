"""Windows composition root for the platform-neutral DS5Forge core."""

from __future__ import annotations

from ...core.config import ConfigRepository
from ...core.facade import CoreFacade
from .audio_capture import WasapiLoopbackFactory
from .dualsense_adapter import PyDualSenseFactory
from .mouse_output import WindowsMouseOutput


def create_windows_facade(*, config_repository: ConfigRepository | None = None) -> CoreFacade:
    return CoreFacade(
        config_repository=config_repository,
        controller_factory=PyDualSenseFactory(),
        capture_factory=WasapiLoopbackFactory(),
        mouse_output=WindowsMouseOutput(),
    )
