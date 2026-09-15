"""Guided, actionable product diagnostics."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class DiagnosticStatus(StrEnum):
    HEALTHY = "healthy"
    WARNING = "warning"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    key: str
    status: DiagnosticStatus
    summary: str
    action: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "status": self.status.value,
            "summary": self.summary,
            "action": self.action,
            "detail": self.detail,
        }


class GuidedDiagnostics:
    """Run a fixed diagnostic inventory with bounded, safe providers."""

    KEYS = (
        "shell",
        "sidecar",
        "api",
        "websocket",
        "usb",
        "capabilities",
        "haptics",
        "foreground",
        "automation",
        "synthetic_output",
        "update",
        "remote",
        "tunnel",
    )

    def __init__(
        self, providers: Mapping[str, Callable[[], DiagnosticCheck | Mapping[str, Any]]] | None = None
    ) -> None:
        self.providers = dict(providers or {})

    def run(self) -> list[DiagnosticCheck]:
        checks: list[DiagnosticCheck] = []
        for key in self.KEYS:
            provider = self.providers.get(key)
            if provider is None:
                checks.append(
                    DiagnosticCheck(
                        key,
                        DiagnosticStatus.NOT_APPLICABLE,
                        "No provider is configured for this check.",
                    )
                )
                continue
            try:
                result = provider()
                if isinstance(result, DiagnosticCheck):
                    checks.append(result)
                else:
                    checks.append(
                        DiagnosticCheck(
                            key,
                            DiagnosticStatus(str(result.get("status", DiagnosticStatus.FAILED))),
                            str(result.get("summary", "Diagnostic provider returned no summary.")),
                            result.get("action"),
                            result.get("detail"),
                        )
                    )
            except Exception:
                checks.append(
                    DiagnosticCheck(
                        key,
                        DiagnosticStatus.FAILED,
                        "The diagnostic provider failed without exposing its exception payload.",
                        "Retry the check and export a Support Bundle if it persists.",
                    )
                )
        return checks

    def to_dict(self) -> dict[str, Any]:
        checks = self.run()
        counts = {status.value: sum(check.status is status for check in checks) for status in DiagnosticStatus}
        overall = DiagnosticStatus.HEALTHY
        if counts[DiagnosticStatus.FAILED.value]:
            overall = DiagnosticStatus.FAILED
        elif counts[DiagnosticStatus.WARNING.value]:
            overall = DiagnosticStatus.WARNING
        elif counts[DiagnosticStatus.UNAVAILABLE.value]:
            overall = DiagnosticStatus.UNAVAILABLE
        elif counts[DiagnosticStatus.NOT_APPLICABLE.value] == len(checks):
            overall = DiagnosticStatus.NOT_APPLICABLE
        return {"status": overall.value, "checks": [check.to_dict() for check in checks], "counts": counts}
