"""Immutable contracts for capability-gated Exclusive input.

Exclusive input is deliberately a separate concern from the legacy P3
``virtual`` compatibility mode.  A provider may expose a virtual DualSense
and still be unsafe to use when physical suppression, provenance or output
report support has not been verified.  These values make that distinction
visible to every client.
"""

from __future__ import annotations

from collections.abc import Mapping as ABCMapping
from dataclasses import dataclass, fields, is_dataclass
from enum import StrEnum
from typing import Any


class ExclusiveMode(StrEnum):
    OFF = "off"
    STARTING = "starting"
    ACTIVE = "active"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ProviderProvenance:
    """Evidence for a fixed, user-installed provider/helper binary."""

    provider: str = "none"
    version: str | None = None
    executable: str | None = None
    sha256: str | None = None
    signature_verified: bool = False
    provenance_verified: bool = False
    integrity_verified: bool = False
    windows_validated: bool = False
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", tuple(str(item) for item in self.evidence))

    @property
    def verified(self) -> bool:
        return bool(
            self.signature_verified and self.provenance_verified and self.integrity_verified and self.windows_validated
        )


@dataclass(frozen=True, slots=True)
class ExclusiveCapability:
    """The complete gate required before Exclusive can become operational."""

    provider_available: bool = False
    provider_installed: bool = False
    virtual_output_reports: bool = False
    physical_output_passthrough: bool = False
    physical_suppression_available: bool = False
    physical_suppression_verified: bool = False
    provenance: ProviderProvenance = ProviderProvenance()
    reason: str = "Exclusive Mode is disabled until a verified Windows provider is available."

    @property
    def operational(self) -> bool:
        return bool(
            self.provider_available
            and self.provider_installed
            and self.virtual_output_reports
            and self.physical_output_passthrough
            and self.physical_suppression_available
            and self.physical_suppression_verified
            and self.provenance.verified
        )

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class ExclusiveStatus:
    """Published runtime status; ownership tokens are never exposed."""

    mode: ExclusiveMode = ExclusiveMode.OFF
    enabled: bool = False
    generation: int = 0
    ownership_acquired: bool = False
    heartbeat_at: float = 0.0
    heartbeat_timeout_ms: int = 1500
    stale: bool = False
    physical_input_visible: bool = True
    virtual_input_active: bool = False
    physical_suppression_active: bool = False
    double_input_risk: bool = True
    capability: ExclusiveCapability = ExclusiveCapability()
    reason: str | None = None
    last_error: str | None = None
    mirrored_sequence: int = 0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class ExclusiveRecovery:
    """Honest result of a pre-session stale-state recovery attempt.

    ``performed`` is only true when local ownership or a provider explicitly
    reported that orphaned session state actually existed.
    """

    performed: bool
    status: ExclusiveStatus
    providers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "providers", tuple(str(item) for item in self.providers))


@dataclass(frozen=True, slots=True)
class DuplicateInputDiagnostic:
    """An honest diagnostic, never a claim that another app is intercepting."""

    risk: bool
    physical_visible: bool
    virtual_active: bool
    suppression_verified: bool
    exclusive_enabled: bool
    severity: str
    message: str
    evidence: tuple[str, ...] = ()
    checked_at: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", tuple(str(item) for item in self.evidence))

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


def _jsonable(value: Any) -> Any:
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
