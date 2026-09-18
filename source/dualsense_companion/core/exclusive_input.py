"""Transactional, capability-gated Exclusive input coordinator.

The coordinator owns the ordering between virtual output and physical input
suppression.  It never shells out, installs a driver or assumes that a
provider is safe because it happens to be present.  Windows adapters implement
the small ports in ``core.ports`` and may be injected by the application.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from ..diagnostics.logging import get_logger
from ..domain.errors import DS5ForgeError, ErrorCode
from ..domain.exclusive import (
    DuplicateInputDiagnostic,
    ExclusiveCapability,
    ExclusiveMode,
    ExclusiveRecovery,
    ExclusiveStatus,
    ProviderProvenance,
)
from ..domain.models import ControllerInput, ControllerReading
from .ports import PhysicalInputSuppressionProvider, PhysicalOutputReportSink, VirtualOutputReportSource

LOGGER = get_logger(__name__)


class ExclusiveCoordinator:
    """Own one provider session and make every transition rollback-safe."""

    def __init__(
        self,
        virtual_provider: VirtualOutputReportSource | None = None,
        suppression_provider: PhysicalInputSuppressionProvider | None = None,
        output_source: VirtualOutputReportSource | None = None,
        physical_output_sink: PhysicalOutputReportSink | None = None,
        *,
        heartbeat_timeout: float = 1.5,
        provider_heartbeat_interval: float = 0.5,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.virtual_provider = virtual_provider
        self.suppression_provider = suppression_provider
        self.output_source = output_source or virtual_provider
        self.physical_output_sink = physical_output_sink
        self.heartbeat_timeout = max(0.25, float(heartbeat_timeout))
        self.provider_heartbeat_interval = max(0.1, min(self.heartbeat_timeout, float(provider_heartbeat_interval)))
        self.clock = clock
        self._lock = threading.RLock()
        self._token: str | None = None
        self._generation = 0
        self._last_heartbeat = 0.0
        self._last_provider_heartbeat = 0.0
        self._mirrored_sequence = 0
        self._status = ExclusiveStatus(heartbeat_timeout_ms=int(self.heartbeat_timeout * 1000))

    def bind_physical_output_sink(self, sink: PhysicalOutputReportSink) -> None:
        """Attach the live controller output path before Exclusive is enabled."""

        with self._lock:
            if self._status.enabled:
                raise RuntimeError("cannot replace the physical output sink while Exclusive is active")
            self.physical_output_sink = sink

    def capability(self) -> ExclusiveCapability:
        """Probe both providers without changing runtime state."""

        with self._lock:
            if self.virtual_provider is None or self.suppression_provider is None:
                return ExclusiveCapability()
            try:
                virtual = self.virtual_provider.capability()
                suppression = self.suppression_provider.capability()
                physical_output = self.physical_output_sink.capability() if self.physical_output_sink is not None else None
            except Exception as exc:
                return ExclusiveCapability(reason=f"Exclusive provider capability probe failed: {exc}")
            provenance = _coerce_provenance(getattr(virtual, "provenance", None), getattr(virtual, "provider", None))
            provider_available = bool(getattr(virtual, "available", False))
            provider_installed = bool(getattr(virtual, "installed", False))
            output_reports = bool(
                getattr(virtual, "output_reports", False) or getattr(virtual, "virtual_output_reports", False)
            )
            physical_output_passthrough = bool(
                physical_output is not None
                and getattr(physical_output, "available", False)
                and getattr(physical_output, "verified", False)
            )
            suppression_available = bool(getattr(suppression, "available", False))
            suppression_verified = bool(
                getattr(suppression, "verified", False) and getattr(suppression, "session_scoped", False)
            )
            reasons = [
                str(getattr(virtual, "reason", "")) if not provider_available else "",
                str(getattr(suppression, "reason", "")) if not suppression_available else "",
                "Provider provenance, signature, integrity and Windows validation are incomplete."
                if not provenance.verified
                else "",
                "Virtual output reports are not proven by the provider." if not output_reports else "",
                str(getattr(physical_output, "reason", ""))
                if not physical_output_passthrough and physical_output is not None
                else (
                    "Physical DualSense output passthrough is unavailable."
                    if not physical_output_passthrough
                    else ""
                ),
                "Physical suppression is not session-verified." if not suppression_verified else "",
            ]
            reason = next((item for item in reasons if item), "Verified provider and suppression are available.")
            return ExclusiveCapability(
                provider_available=provider_available,
                provider_installed=provider_installed,
                virtual_output_reports=output_reports,
                physical_output_passthrough=physical_output_passthrough,
                physical_suppression_available=suppression_available,
                physical_suppression_verified=suppression_verified,
                provenance=provenance,
                reason=reason,
            )

    def status(self) -> ExclusiveStatus:
        with self._lock:
            capability = self.capability()
            return replace(self._status, capability=capability)

    def enable(self) -> ExclusiveStatus:
        with self._lock:
            capability = self.capability()
            if not capability.operational:
                status = replace(
                    self._status,
                    mode=ExclusiveMode.OFF,
                    enabled=False,
                    ownership_acquired=False,
                    physical_input_visible=True,
                    virtual_input_active=False,
                    physical_suppression_active=False,
                    double_input_risk=True,
                    capability=capability,
                    reason=capability.reason,
                    last_error=None,
                    updated_at=self.clock(),
                )
                self._status = status
                raise DS5ForgeError(
                    ErrorCode.EXCLUSIVE_UNAVAILABLE,
                    "Exclusive Mode is unavailable until provider and suppression validation pass.",
                    detail=capability.reason,
                    fields={"capability": capability.to_dict()},
                )
            if self._status.enabled:
                return self._status
            self._generation += 1
            token = secrets.token_urlsafe(32)
            self._status = replace(
                self._status,
                mode=ExclusiveMode.STARTING,
                generation=self._generation,
                ownership_acquired=False,
                capability=capability,
                reason=None,
                last_error=None,
                updated_at=self.clock(),
            )
            virtual_started = False
            physical_output_started = False
            suppression_started = False
            try:
                virtual_provider = self.virtual_provider
                suppression_provider = self.suppression_provider
                physical_output_sink = self.physical_output_sink
                assert virtual_provider is not None
                assert suppression_provider is not None
                assert physical_output_sink is not None
                # Mark each step before calling into an external provider.
                # Providers can fail after partially acquiring state; cleanup
                # methods are required to be idempotent and will then release
                # that partial acquisition during rollback.
                virtual_started = True
                virtual_provider.start(token=token, generation=self._generation)
                physical_output_started = True
                physical_output_sink.begin(token=token, generation=self._generation)
                suppression_started = True
                suppression_provider.enable(token=token, generation=self._generation)
                self._token = token
                self._last_heartbeat = self.clock()
                self._last_provider_heartbeat = self._last_heartbeat
                self._status = replace(
                    self._status,
                    mode=ExclusiveMode.ACTIVE,
                    enabled=True,
                    ownership_acquired=True,
                    heartbeat_at=self._last_heartbeat,
                    stale=False,
                    physical_input_visible=False,
                    virtual_input_active=True,
                    physical_suppression_active=True,
                    double_input_risk=False,
                    updated_at=self._last_heartbeat,
                )
                return self._status
            except Exception as exc:
                # Suppression is enabled second so a virtual device can never
                # be left active when the physical side fails.
                if suppression_started and suppression_provider is not None:
                    _best_effort(lambda: suppression_provider.disable(token=token, generation=self._generation))
                if physical_output_started and physical_output_sink is not None:
                    _best_effort(lambda: physical_output_sink.end(token=token, generation=self._generation))
                if virtual_started and virtual_provider is not None:
                    _best_effort(lambda: virtual_provider.close(token=token, generation=self._generation))
                self._token = None
                self._status = replace(
                    self._status,
                    mode=ExclusiveMode.ERROR,
                    enabled=False,
                    ownership_acquired=False,
                    physical_input_visible=True,
                    virtual_input_active=False,
                    physical_suppression_active=False,
                    double_input_risk=True,
                    reason="Exclusive transaction rolled back after a provider failure.",
                    last_error=str(exc),
                    updated_at=self.clock(),
                )
                raise DS5ForgeError(
                    ErrorCode.EXCLUSIVE_ROLLBACK,
                    "Exclusive Mode could not start and was rolled back safely.",
                    detail=str(exc),
                    fields={"generation": self._generation},
                ) from exc

    def disable(self, *, reason: str = "manual") -> ExclusiveStatus:
        with self._lock:
            token = self._token
            generation = self._generation
            self._status = replace(self._status, mode=ExclusiveMode.STOPPING, updated_at=self.clock())
            failures: list[str] = []
            suppression_provider = self.suppression_provider
            virtual_provider = self.virtual_provider
            physical_output_sink = self.physical_output_sink
            # Remove the virtual device before revealing the physical one. A
            # short no-input window is safer than a short duplicate-input
            # window, and every teardown step remains best-effort/idempotent.
            if token is not None and virtual_provider is not None:
                try:
                    virtual_provider.close(token=token, generation=generation)
                except Exception as exc:
                    failures.append(f"virtual: {exc}")
            if token is not None and physical_output_sink is not None:
                try:
                    physical_output_sink.end(token=token, generation=generation)
                except Exception as exc:
                    failures.append(f"physical_output: {exc}")
            if token is not None and suppression_provider is not None:
                try:
                    suppression_provider.disable(token=token, generation=generation)
                except Exception as exc:
                    failures.append(f"suppression: {exc}")
            self._token = None
            now = self.clock()
            self._status = replace(
                self._status,
                mode=ExclusiveMode.ERROR if failures else ExclusiveMode.OFF,
                enabled=False,
                ownership_acquired=False,
                stale=False,
                physical_input_visible=True,
                virtual_input_active=False,
                physical_suppression_active=False,
                double_input_risk=True,
                reason=(f"Disabled ({reason})." if not failures else f"Teardown incomplete: {'; '.join(failures)}"),
                last_error=(
                    "; ".join(failures)
                    if failures
                    else (None if reason == "manual" else f"Exclusive session ended: {reason}.")
                ),
                updated_at=now,
            )
            return self._status

    def heartbeat(self) -> ExclusiveStatus:
        """Public/API liveness probe.

        It refreshes only the *provider* liveness contract (and even that is
        throttled); it deliberately does not refresh the authoritative core
        mirror lease. Only a successful :meth:`mirror_reading` proves that the
        physical read/mirror path is still alive, so repeatedly calling this
        endpoint cannot keep a stalled Exclusive session from expiring.
        """

        with self._lock:
            if not self._status.enabled or self._token is None:
                return self._status
            current = self.clock()
            if current - self._last_provider_heartbeat >= self.provider_heartbeat_interval:
                return self._provider_heartbeat_locked(current)
            return self._status

    def _provider_heartbeat_locked(self, current: float) -> ExclusiveStatus:
        token = self._token
        if token is None:
            return self._status
        try:
            virtual_provider = self.virtual_provider
            suppression_provider = self.suppression_provider
            if virtual_provider is not None:
                virtual_provider.heartbeat(token=token, generation=self._generation)
            if suppression_provider is not None:
                suppression_provider.heartbeat(token=token, generation=self._generation)
        except Exception as exc:
            LOGGER.warning(
                "exclusive provider heartbeat failed", extra={"event": "exclusive.heartbeat", "error": str(exc)}
            )
            self.disable(reason="heartbeat_failed")
            return replace(self._status, stale=True, last_error=str(exc))
        self._last_provider_heartbeat = current
        self._status = replace(self._status, stale=False, updated_at=current)
        return self._status

    def tick(self, *, now: float | None = None) -> ExclusiveStatus:
        """Bounded monitor step independent of the controller read callback.

        It sends the (throttled) provider heartbeat and enforces the core lease
        so that a stalled read/mirror path expires the session instead of
        silently keeping physical input suppressed.
        """

        with self._lock:
            if not self._status.enabled or self._token is None:
                # No capability re-probe here: the watchdog runs at a bounded
                # cadence and provider provenance probing can be expensive.
                return self._status
            current = self.clock() if now is None else float(now)
            if current - self._last_provider_heartbeat >= self.provider_heartbeat_interval:
                status = self._provider_heartbeat_locked(current)
                if status.stale:
                    return status
            if current - self._last_heartbeat > self.heartbeat_timeout:
                return self.disable(reason="heartbeat_timeout")
            return self._status

    def watchdog(self, *, now: float | None = None) -> ExclusiveStatus:
        with self._lock:
            if not self._status.enabled:
                return self._status
            current = self.clock() if now is None else float(now)
            if current - self._last_heartbeat <= self.heartbeat_timeout:
                return self._status
        return self.disable(reason="heartbeat_timeout")

    def mirror_reading(self, reading: ControllerReading) -> ExclusiveStatus:
        with self._lock:
            if not self._status.enabled or self._token is None or self.output_source is None:
                return self._status
            try:
                output_reports = self.output_source.submit_state(
                    reading.input,
                    battery=reading.battery,
                    sequence=self._mirrored_sequence + 1,
                    token=self._token,
                    generation=self._generation,
                )
                if output_reports:
                    physical_output_sink = self.physical_output_sink
                    if physical_output_sink is None:
                        raise RuntimeError("Exclusive physical output sink disappeared while active")
                    for report in output_reports:
                        physical_output_sink.submit(
                            bytes(report),
                            token=self._token,
                            generation=self._generation,
                        )
                self._mirrored_sequence += 1
                # A successful mirror is the liveness proof for the core lease;
                # the provider heartbeat is throttled separately in tick().
                self._last_heartbeat = self.clock()
                self._status = replace(
                    self._status,
                    mirrored_sequence=self._mirrored_sequence,
                    heartbeat_at=self._last_heartbeat,
                    updated_at=self._last_heartbeat,
                )
            except Exception as exc:
                self.disable(reason="mirror_failed")
                raise DS5ForgeError(
                    ErrorCode.EXCLUSIVE_MIRROR_FAILED,
                    "Exclusive input mirroring failed and was disabled.",
                    detail=str(exc),
                ) from exc
            return self._status

    def recover(self) -> ExclusiveRecovery:
        """Clean orphaned helper/provider state before a new session starts.

        Returns whether anything was actually recovered so callers do not
        publish a misleading ``exclusive.recovered`` event when nothing was.
        """

        with self._lock:
            recovered_providers: list[str] = []
            local_orphan = self._token is not None or self._status.enabled
            for name, provider in (
                ("suppression", self.suppression_provider),
                ("virtual", self.virtual_provider),
            ):
                recover = getattr(provider, "recover_stale", None)
                if not callable(recover):
                    continue
                try:
                    result = recover()
                except Exception as exc:
                    LOGGER.warning(
                        "stale exclusive state recovery failed",
                        extra={"event": "exclusive.recovery", "error": str(exc)},
                    )
                    continue
                if result is True:
                    recovered_providers.append(name)
            if local_orphan:
                self._token = None
                self._status = replace(
                    self._status,
                    mode=ExclusiveMode.OFF,
                    enabled=False,
                    ownership_acquired=False,
                    stale=False,
                    physical_input_visible=True,
                    virtual_input_active=False,
                    physical_suppression_active=False,
                    double_input_risk=True,
                    updated_at=self.clock(),
                )
            performed = local_orphan or bool(recovered_providers)
            return ExclusiveRecovery(performed=performed, status=self.status(), providers=tuple(recovered_providers))

    def recover_stale(self) -> ExclusiveStatus:
        """Backwards-compatible wrapper that only returns the resulting status."""

        return self.recover().status

    def duplicate_input_diagnostic(self) -> DuplicateInputDiagnostic:
        status = self.status()
        if status.enabled and status.physical_suppression_active and not status.double_input_risk:
            severity = "success"
            message = "Physical input suppression is session-verified for the active Exclusive session."
        elif status.capability.operational:
            severity = "warning"
            message = "Exclusive is available but not active; the physical controller remains visible."
        else:
            severity = "warning"
            message = "Physical suppression is not verified; duplicate input risk remains true."
        return DuplicateInputDiagnostic(
            risk=status.double_input_risk,
            physical_visible=status.physical_input_visible,
            virtual_active=status.virtual_input_active,
            suppression_verified=status.capability.physical_suppression_verified,
            exclusive_enabled=status.enabled,
            severity=severity,
            message=message,
            evidence=status.capability.provenance.evidence,
            checked_at=time.time(),
        )


def _coerce_provenance(value: Any, provider: Any) -> ProviderProvenance:
    if isinstance(value, ProviderProvenance):
        return value
    if value is None:
        return ProviderProvenance(provider=str(provider or "none"))
    if isinstance(value, dict):
        allowed = {field for field in ProviderProvenance.__dataclass_fields__}
        return ProviderProvenance(**{key: item for key, item in value.items() if key in allowed})
    return ProviderProvenance(provider=str(provider or "unknown"))


def _best_effort(action: Callable[[], Any]) -> None:
    try:
        action()
    except Exception:
        LOGGER.exception("exclusive rollback cleanup failed", extra={"event": "exclusive.rollback_cleanup"})


class FakeExclusiveVirtualProvider:
    """Deterministic test provider; never represents a production capability."""

    def __init__(self, *, fail_start: bool = False, output_reports: bool = True) -> None:
        self.fail_start = fail_start
        self.started = False
        self.states: list[dict[str, Any]] = []
        self.output_reports: list[bytes] = []
        self._capability = type(
            "Capability",
            (),
            {
                "available": True,
                "installed": True,
                "output_reports": output_reports,
                "provider": "fake-exclusive",
                "provenance": ProviderProvenance(
                    provider="fake-exclusive",
                    signature_verified=True,
                    provenance_verified=True,
                    integrity_verified=True,
                    windows_validated=True,
                    evidence=("deterministic test fake",),
                ),
                "reason": None,
            },
        )()

    def capability(self) -> Any:
        return self._capability

    def start(self, *, token: str, generation: int) -> None:
        if self.fail_start:
            raise RuntimeError("fake virtual provider start failure")
        self.started = True

    def heartbeat(self, *, token: str, generation: int) -> None:
        if not self.started:
            raise RuntimeError("fake virtual provider is not started")

    def submit_state(
        self, input_state: ControllerInput, *, battery: Any, sequence: int, token: str, generation: int
    ) -> tuple[bytes, ...]:
        if not self.started:
            raise RuntimeError("fake virtual provider is not started")
        self.states.append({"input": input_state.to_dict(), "battery": battery.to_dict(), "sequence": sequence})
        reports = tuple(self.output_reports)
        self.output_reports.clear()
        return reports

    def queue_output_report(self, report: bytes) -> None:
        self.output_reports.append(bytes(report))

    def close(self, *, token: str, generation: int) -> None:
        self.started = False

    def recover_stale(self) -> bool:
        recovered = self.started or bool(self.states)
        self.started = False
        return recovered


class FakePhysicalOutputReportSink:
    def __init__(self, *, verified: bool = True, fail_begin: bool = False, events: list[str] | None = None) -> None:
        self.active = False
        self.fail_begin = fail_begin
        self.reports: list[bytes] = []
        self.events = events
        self._capability = type(
            "PhysicalOutputCapability",
            (),
            {
                "available": True,
                "verified": verified,
                "reason": None if verified else "fake physical output passthrough is intentionally unverified",
            },
        )()

    def capability(self) -> Any:
        return self._capability

    def begin(self, *, token: str, generation: int) -> None:
        del token, generation
        if self.fail_begin:
            raise RuntimeError("fake physical output passthrough start failure")
        self.active = True
        if self.events is not None:
            self.events.append("physical_output.begin")

    def submit(self, report: bytes, *, token: str, generation: int) -> None:
        del token, generation
        if not self.active:
            raise RuntimeError("fake physical output passthrough is not active")
        self.reports.append(bytes(report))

    def end(self, *, token: str, generation: int) -> None:
        del token, generation
        self.active = False
        if self.events is not None:
            self.events.append("physical_output.end")


class FakePhysicalSuppressionProvider:
    def __init__(self, *, verified: bool = True, fail_enable: bool = False) -> None:
        self.started = False
        self.fail_enable = fail_enable
        self._capability = type(
            "SuppressionCapability",
            (),
            {
                "available": True,
                "verified": verified,
                "session_scoped": True,
                "reason": None if verified else "fake suppression is intentionally unverified",
            },
        )()

    def capability(self) -> Any:
        return self._capability

    def enable(self, *, token: str, generation: int) -> None:
        if self.fail_enable:
            raise RuntimeError("fake suppression enable failure")
        self.started = True

    def heartbeat(self, *, token: str, generation: int) -> None:
        if not self.started:
            raise RuntimeError("fake suppression is not started")

    def disable(self, *, token: str, generation: int) -> None:
        self.started = False

    def recover_stale(self) -> bool:
        recovered = self.started
        self.started = False
        return recovered
