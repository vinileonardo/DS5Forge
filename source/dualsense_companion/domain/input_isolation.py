"""Contracts for explicit physical-controller isolation used to fix double input.

This is intentionally separate from P5 Exclusive virtual-controller ownership.
HidHide can suppress the physical DualSense for ordinary applications while
allowing DS5Forge to continue reading it, which is useful for Remap. It does
not create a virtual DualSense and must never be presented as Exclusive mode.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class InputIsolationCapability:
    provider: str = "HidHide"
    installed: bool = False
    available: bool = False
    version: str | None = None
    executable: str | None = None
    application_path: str | None = None
    device_detected: bool = False
    device_instance_path: str | None = None
    reason: str | None = "HidHide is not available."

    @property
    def operational(self) -> bool:
        return bool(
            self.installed
            and self.available
            and self.application_path
            and self.device_detected
            and self.device_instance_path
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class InputIsolationStatus:
    active: bool = False
    owned: bool = False
    cloak_enabled: bool = False
    application_registered: bool = False
    device_hidden: bool = False
    physical_input_visible: bool = True
    double_input_risk: bool = True
    device_instance_path: str | None = None
    capability: InputIsolationCapability = InputIsolationCapability()
    reason: str | None = None
    last_error: str | None = None
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
