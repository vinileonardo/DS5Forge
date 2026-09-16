"""Typed errors crossing the core, API and platform boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import ErrorSnapshot


class ErrorCode(StrEnum):
    CONFIG_INVALID = "config.invalid"
    CONFIG_LOAD_FAILED = "config.load_failed"
    CONFIG_SAVE_FAILED = "config.save_failed"
    PROFILE_INVALID = "profile.invalid"
    PROFILE_NOT_FOUND = "profile.not_found"
    PROFILE_OVERWRITE_REQUIRED = "profile.overwrite_required"
    PROFILE_IMPORT_TOO_LARGE = "profile.import_too_large"
    CONTROLLER_UNAVAILABLE = "controller.unavailable"
    CONTROLLER_CONNECT_FAILED = "controller.connect_failed"
    CONTROLLER_READ_FAILED = "controller.read_failed"
    CONTROLLER_OUTPUT_FAILED = "controller.output_failed"
    CAPABILITY_UNSUPPORTED = "capability.unsupported"
    LIGHTBAR_OUTPUT_FAILED = "lightbar.output_failed"
    TRIGGER_OUTPUT_FAILED = "trigger.output_failed"
    TRIGGER_PREVIEW_BUSY = "trigger.preview_busy"
    HAPTICS_TEST_BUSY = "haptics.test_busy"
    HAPTICS_TEST_FAILED = "haptics.test_failed"
    AUDIO_UNAVAILABLE = "audio.unavailable"
    AUDIO_CAPTURE_FAILED = "audio.capture_failed"
    POINTER_OUTPUT_FAILED = "pointer.output_failed"
    SYNTHETIC_OUTPUT_FAILED = "synthetic.output_failed"
    GAME_REGISTRY_INVALID = "game_registry.invalid"
    GAME_REGISTRY_LOAD_FAILED = "game_registry.load_failed"
    GAME_REGISTRY_SAVE_FAILED = "game_registry.save_failed"
    GAME_NOT_FOUND = "game.not_found"
    MAPPING_CONFLICT = "mapping.conflict"
    CHORD_CONFLICT = "chord.conflict"
    FOREGROUND_UNAVAILABLE = "foreground.unavailable"
    COMPATIBILITY_UNAVAILABLE = "compatibility.unavailable"
    VIRTUAL_PROVIDER_UNAVAILABLE = "virtual_provider.unavailable"
    EXCLUSIVE_UNAVAILABLE = "exclusive.unavailable"
    EXCLUSIVE_ROLLBACK = "exclusive.rollback"
    EXCLUSIVE_MIRROR_FAILED = "exclusive.mirror_failed"
    EXCLUSIVE_HEARTBEAT_FAILED = "exclusive.heartbeat_failed"
    PLATFORM_UNAVAILABLE = "platform.unavailable"
    API_VALIDATION = "api.validation"
    INTERNAL = "internal.error"


class DS5ForgeError(Exception):
    """An expected operational error with a stable code and safe message."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        detail: str | None = None,
        recoverable: bool = True,
        fields: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail
        self.recoverable = recoverable
        self.fields = dict(fields or {})

    def to_snapshot(self) -> ErrorSnapshot:
        # Imported lazily to keep this module usable during model bootstrap.
        from .models import ErrorSnapshot

        return ErrorSnapshot(
            code=self.code,
            message=self.message,
            detail=self.detail,
            recoverable=self.recoverable,
            fields=self.fields,
        )


class ConfigValidationError(DS5ForgeError):
    def __init__(
        self,
        message: str = "Configuration is invalid.",
        *,
        fields: Mapping[str, Any] | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(
            ErrorCode.CONFIG_INVALID,
            message,
            detail=detail,
            recoverable=True,
            fields=fields,
        )


class ControllerUnavailableError(DS5ForgeError):
    def __init__(self, message: str = "No USB controller is available.", *, detail: str | None = None) -> None:
        super().__init__(ErrorCode.CONTROLLER_UNAVAILABLE, message, detail=detail, recoverable=True)


class ProfileInvalidError(DS5ForgeError):
    """Raised when a persisted or imported profile cannot be trusted."""

    def __init__(
        self,
        message: str = "Profile is invalid and was not applied.",
        *,
        detail: str | None = None,
        fields: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(ErrorCode.PROFILE_INVALID, message, detail=detail, recoverable=True, fields=fields)


class PlatformUnavailableError(DS5ForgeError):
    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(ErrorCode.PLATFORM_UNAVAILABLE, message, detail=detail, recoverable=True)


class CapabilityUnavailableError(DS5ForgeError):
    """Raised before a hardware operation when the adapter cannot support it."""

    def __init__(self, capability: str, reason: str | None = None) -> None:
        message = f"The controller does not support {capability}."
        super().__init__(
            ErrorCode.CAPABILITY_UNSUPPORTED,
            message,
            detail=reason,
            recoverable=True,
            fields={"capability": capability, "reason": reason or "Capability is unavailable."},
        )
