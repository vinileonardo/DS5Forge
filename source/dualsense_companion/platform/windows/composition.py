"""Windows composition root for the platform-neutral DS5Forge core."""

from __future__ import annotations

from pathlib import Path

from ...core.config import ConfigRepository
from ...core.exclusive_input import ExclusiveCoordinator
from ...core.facade import CoreFacade
from ...core.input_isolation import InputIsolationCoordinator
from .audio_capture import WasapiLoopbackFactory
from .dualsense_adapter import PyDualSenseFactory
from .exclusive_provider import (
    FixedExclusiveSidecarClient,
    FixedSidecarVerifier,
    WindowsHidHideSuppressionProvider,
    WindowsHidMaestroProvider,
)
from .foreground import WindowsForegroundDetector
from .hidhide import WindowsHidHideIsolationProvider
from .keyboard_output import WindowsKeyboardOutput
from .mouse_output import WindowsMouseOutput
from .process_diagnostics import WindowsProcessInspector


def create_windows_exclusive_coordinator(
    *,
    helper_path: Path | None = None,
    expected_sha256: str | None = None,
    signature_verified: bool = False,
    provenance_verified: bool = False,
    windows_validated: bool = False,
) -> ExclusiveCoordinator:
    """Compose the investigated provider without making it operational by default."""

    verifier = FixedSidecarVerifier(
        helper_path,
        expected_sha256=expected_sha256,
        signature_verified=signature_verified,
        provenance_verified=provenance_verified,
        windows_validated=windows_validated,
    )
    client = FixedExclusiveSidecarClient(verifier)
    return ExclusiveCoordinator(
        virtual_provider=WindowsHidMaestroProvider(client),
        suppression_provider=WindowsHidHideSuppressionProvider(client),
    )


def create_windows_facade(
    *,
    config_repository: ConfigRepository | None = None,
    exclusive_coordinator: ExclusiveCoordinator | None = None,
) -> CoreFacade:
    return CoreFacade(
        config_repository=config_repository,
        controller_factory=PyDualSenseFactory(),
        capture_factory=WasapiLoopbackFactory(),
        mouse_output=WindowsMouseOutput(),
        keyboard_output=WindowsKeyboardOutput(),
        foreground_detector=WindowsForegroundDetector(),
        process_inspector=WindowsProcessInspector(),
        exclusive_coordinator=exclusive_coordinator or create_windows_exclusive_coordinator(),
        input_isolation=InputIsolationCoordinator(WindowsHidHideIsolationProvider()),
    )
