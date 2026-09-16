"""Platform-neutral coordinator for explicit Remap physical-input isolation."""

from __future__ import annotations

from ..domain.errors import DS5ForgeError, ErrorCode
from ..domain.input_isolation import InputIsolationCapability, InputIsolationStatus
from .ports import PhysicalInputIsolationProvider


class InputIsolationCoordinator:
    def __init__(self, provider: PhysicalInputIsolationProvider | None = None) -> None:
        self.provider = provider

    def capability(self) -> InputIsolationCapability:
        if self.provider is None:
            return InputIsolationCapability()
        try:
            return self.provider.capability()
        except Exception as exc:
            return InputIsolationCapability(reason=f"Input isolation capability probe failed: {exc}")

    def status(self) -> InputIsolationStatus:
        if self.provider is None:
            capability = self.capability()
            return InputIsolationStatus(capability=capability, reason=capability.reason)
        try:
            return self.provider.status()
        except Exception as exc:
            capability = self.capability()
            return InputIsolationStatus(
                capability=capability,
                reason="Input isolation status could not be verified.",
                last_error=str(exc),
            )

    def enable(self) -> InputIsolationStatus:
        capability = self.capability()
        if self.provider is None or not capability.operational:
            raise DS5ForgeError(
                ErrorCode.INPUT_ISOLATION_UNAVAILABLE,
                "Physical input isolation is unavailable.",
                detail=capability.reason,
                fields={"capability": capability.to_dict()},
            )
        try:
            status = self.provider.enable()
        except Exception as exc:
            raise DS5ForgeError(
                ErrorCode.INPUT_ISOLATION_FAILED,
                "Physical input isolation could not be enabled and was rolled back.",
                detail=str(exc),
            ) from exc
        if not status.active:
            raise DS5ForgeError(
                ErrorCode.INPUT_ISOLATION_FAILED,
                "Physical input isolation could not be verified after enabling.",
                detail=status.last_error or status.reason,
            )
        return status

    def disable(self) -> InputIsolationStatus:
        if self.provider is None:
            return self.status()
        try:
            return self.provider.disable()
        except Exception as exc:
            raise DS5ForgeError(
                ErrorCode.INPUT_ISOLATION_FAILED,
                "Physical input isolation teardown was incomplete.",
                detail=str(exc),
            ) from exc

    def recover_stale(self) -> tuple[bool, InputIsolationStatus]:
        if self.provider is None:
            return False, self.status()
        try:
            recovered = bool(self.provider.recover_stale())
        except Exception as exc:
            raise DS5ForgeError(
                ErrorCode.INPUT_ISOLATION_FAILED,
                "Stale physical input isolation could not be recovered.",
                detail=str(exc),
            ) from exc
        return recovered, self.status()
