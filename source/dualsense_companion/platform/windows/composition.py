"""Windows composition root for the platform-neutral DS5Forge core."""

from __future__ import annotations

from ...core.config import ConfigRepository
from ...core.facade import CoreFacade
from .audio_capture import WasapiLoopbackFactory
from .dualsense_adapter import PyDualSenseFactory
from .foreground import WindowsForegroundDetector
from .keyboard_output import WindowsKeyboardOutput
from .mouse_output import WindowsMouseOutput
from .process_diagnostics import WindowsProcessInspector


def create_windows_facade(*, config_repository: ConfigRepository | None = None) -> CoreFacade:
    return CoreFacade(
        config_repository=config_repository,
        controller_factory=PyDualSenseFactory(),
        capture_factory=WasapiLoopbackFactory(),
        mouse_output=WindowsMouseOutput(),
        keyboard_output=WindowsKeyboardOutput(),
        foreground_detector=WindowsForegroundDetector(),
        process_inspector=WindowsProcessInspector(),
    )
