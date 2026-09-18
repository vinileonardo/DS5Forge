"""Capability-gated Adaptive Trigger arbitration.

Controller Lab owns explicit user previews; this engine owns runtime sources.
Only one resolved effect reaches hardware.  Every source has a bounded TTL,
updates are coalesced, and transitions/reset always write Off when possible.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
from enum import IntEnum, StrEnum
from typing import Any, Protocol

from ..diagnostics.logging import get_logger
from ..domain.errors import CapabilityUnavailableError
from ..domain.models import AdaptiveTriggerEffect, ControllerInput, TriggerState

LOGGER = get_logger(__name__)


class TriggerSource(StrEnum):
    GAME_NATIVE = "game_native"
    TELEMETRY = "telemetry"
    REACTIVE = "reactive"
    OFF = "off"


class TriggerPriority(IntEnum):
    OFF = 0
    REACTIVE = 10
    TELEMETRY = 20
    GAME_NATIVE = 30


@dataclass(frozen=True, slots=True)
class TriggerRequest:
    source: TriggerSource
    state: TriggerState
    expires_at: float
    generated: bool = False
    label: str | None = None


@dataclass(frozen=True, slots=True)
class AdaptiveTriggerStatus:
    source: TriggerSource = TriggerSource.OFF
    state: TriggerState = TriggerState()
    expires_at: float = 0.0
    generated_effect: bool = False
    output_supported: bool = False
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.value,
            "state": self.state.to_dict(),
            "expires_at": self.expires_at,
            "generated_effect": self.generated_effect,
            "output_supported": self.output_supported,
            "reason": self.reason,
        }


class TriggerOutput(Protocol):
    def set_triggers(self, state: TriggerState) -> None: ...

    def reset_triggers(self) -> None: ...


class TelemetryAdapter(Protocol):
    def trigger_state(self, telemetry: Mapping[str, Any], *, now: float) -> TriggerState | None: ...


class AdaptiveTriggerEngine:
    """Arbitrate runtime effects in priority order with watchdog cleanup."""

    def __init__(
        self,
        output: TriggerOutput,
        *,
        output_supported: bool,
        ttl_seconds: float = 1.5,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.output = output
        self.output_supported = bool(output_supported)
        self.ttl_seconds = max(0.1, float(ttl_seconds))
        self.clock = clock
        self._lock = threading.RLock()
        self._requests: dict[TriggerSource, TriggerRequest] = {}
        self._resolved = TriggerState()
        self._status = AdaptiveTriggerStatus(output_supported=self.output_supported)

    @property
    def status(self) -> AdaptiveTriggerStatus:
        with self._lock:
            return self._status

    def set_output_supported(self, supported: bool) -> AdaptiveTriggerStatus:
        """Re-evaluate capability after the controller connection changes."""

        with self._lock:
            self.output_supported = bool(supported)
            if not self.output_supported:
                self._requests.clear()
                if self._resolved != TriggerState():
                    self._safe_reset_locked()
                self._resolved = TriggerState()
            self._status = dataclass_replace(self._status, output_supported=self.output_supported)
            return self._status

    def set_source(
        self,
        source: TriggerSource | str,
        state: TriggerState,
        *,
        ttl_seconds: float | None = None,
        generated_effect: bool = False,
        label: str | None = None,
        now: float | None = None,
    ) -> AdaptiveTriggerStatus:
        source = TriggerSource(source)
        if source == TriggerSource.OFF:
            return self.reset(reason="off_source")
        if not self.output_supported:
            raise CapabilityUnavailableError("adaptive_triggers", "Output-report support is not proven.")
        current = self.clock() if now is None else float(now)
        expires = current + max(0.1, float(ttl_seconds if ttl_seconds is not None else self.ttl_seconds))
        with self._lock:
            self._requests[source] = TriggerRequest(source, state, expires, generated_effect, label)
            self._resolve_locked(current)
            return self._status

    def clear_source(self, source: TriggerSource | str, *, reason: str = "source_clear") -> AdaptiveTriggerStatus:
        with self._lock:
            self._requests.pop(TriggerSource(source), None)
            self._resolve_locked(self.clock(), reason=reason)
            return self._status

    def set_game_native(self, state: TriggerState, *, ttl_seconds: float | None = None) -> AdaptiveTriggerStatus:
        return self.set_source(TriggerSource.GAME_NATIVE, state, ttl_seconds=ttl_seconds, label="native output")

    def set_telemetry(self, state: TriggerState, *, ttl_seconds: float | None = None) -> AdaptiveTriggerStatus:
        return self.set_source(TriggerSource.TELEMETRY, state, ttl_seconds=ttl_seconds, label="telemetry adapter")

    def set_reactive(self, state: TriggerState, *, ttl_seconds: float | None = None) -> AdaptiveTriggerStatus:
        return self.set_source(
            TriggerSource.REACTIVE,
            state,
            ttl_seconds=ttl_seconds,
            generated_effect=True,
            label="DS5Forge-generated reactive effect",
        )

    def tick(self, *, now: float | None = None) -> AdaptiveTriggerStatus:
        with self._lock:
            self._resolve_locked(self.clock() if now is None else float(now), reason="watchdog")
            return self._status

    def reset(self, *, reason: str = "reset", force: bool = False) -> AdaptiveTriggerStatus:
        """Clear every source and release DS5Forge trigger ownership.

        ``force`` writes a neutral report even when this engine believes it has
        not resolved an effect yet. It is used for explicit ``off`` ownership
        and for the start of a ``reactive`` session so stale static profile
        effects written by an earlier manual apply cannot leak through.
        """

        with self._lock:
            self._requests.clear()
            if force or self._resolved != TriggerState():
                self._safe_reset_locked()
            self._resolved = TriggerState()
            self._status = AdaptiveTriggerStatus(
                source=TriggerSource.OFF,
                state=TriggerState(),
                output_supported=self.output_supported,
                reason=reason,
            )
            return self._status

    def _resolve_locked(self, now: float, *, reason: str | None = None) -> None:
        expired = [source for source, request in self._requests.items() if request.expires_at <= now]
        for source in expired:
            self._requests.pop(source, None)
        winner = max(
            self._requests.values(),
            key=lambda item: {
                TriggerSource.GAME_NATIVE: TriggerPriority.GAME_NATIVE,
                TriggerSource.TELEMETRY: TriggerPriority.TELEMETRY,
                TriggerSource.REACTIVE: TriggerPriority.REACTIVE,
            }[item.source],
            default=None,
        )
        next_state = winner.state if winner else TriggerState()
        if next_state == self._resolved:
            if winner is None and self._status.source != TriggerSource.OFF:
                self._safe_reset_locked()
                self._status = AdaptiveTriggerStatus(
                    source=TriggerSource.OFF,
                    state=TriggerState(),
                    output_supported=self.output_supported,
                    reason=reason or "no active source",
                )
            elif winner is not None:
                # Refreshing a source's request extends its watchdog without
                # sending a duplicate hardware report when the resolved state
                # itself did not change.
                self._status = AdaptiveTriggerStatus(
                    source=winner.source,
                    state=next_state,
                    expires_at=winner.expires_at,
                    generated_effect=winner.generated,
                    output_supported=self.output_supported,
                    reason=winner.label,
                )
            return
        try:
            if winner is None:
                self._safe_reset_locked()
            else:
                self.output.set_triggers(next_state)
        except Exception:
            self._safe_reset_locked()
            self._requests.clear()
            self._resolved = TriggerState()
            raise
        self._resolved = next_state
        self._status = AdaptiveTriggerStatus(
            source=winner.source if winner else TriggerSource.OFF,
            state=next_state,
            expires_at=winner.expires_at if winner else 0.0,
            generated_effect=winner.generated if winner else False,
            output_supported=self.output_supported,
            reason=(winner.label if winner else reason),
        )

    def _safe_reset_locked(self) -> None:
        if not self.output_supported:
            return
        try:
            self.output.reset_triggers()
        except Exception:
            LOGGER.exception("adaptive trigger reset failed", extra={"event": "adaptive_triggers.reset"})


class FakeTelemetryAdapter:
    """Deterministic adapter for a game/telemetry integration test."""

    def __init__(self, *, force: int = 90) -> None:
        self.force = max(0, min(255, int(force)))

    def trigger_state(self, telemetry: Mapping[str, Any], *, now: float) -> TriggerState | None:
        impact = float(telemetry.get("impact", 0.0))
        if impact <= 0:
            return None
        effect = AdaptiveTriggerEffect(mode="resistance", force=min(255, int(self.force * impact)))
        return TriggerState(left=effect, right=effect)


@dataclass(slots=True)
class _ReactivePulse:
    until: float = 0.0
    energy: float = 0.0
    frequency: int = 0


class ReactiveTriggerAdapter:
    """Generic generated effects that stay honest about the signals we own.

    The adapter deliberately does not invent semantic game events. It turns
    real trigger travel and the real audio envelope into a more varied tactile
    vocabulary:

    * each side reacts independently;
    * normal travel uses a progressive feedback-zone resistance;
    * a fresh trigger engagement produces a short kick;
    * a sharp audio transient can add a brief pulse while that trigger is held.

    Audio by itself never makes both triggers permanently stiff.
    """

    PRESS_THRESHOLD = 0.06
    KICK_THRESHOLD = 0.16
    AUDIO_TRANSIENT_THRESHOLD = 0.12
    KICK_SECONDS = 0.075
    AUDIO_PULSE_SECONDS = 0.060

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._previous_audio = 0.0
        self._previous_press = {"left": 0.0, "right": 0.0}
        self._pulse = {"left": _ReactivePulse(), "right": _ReactivePulse()}

    def reset(self) -> None:
        self._previous_audio = 0.0
        self._previous_press = {"left": 0.0, "right": 0.0}
        self._pulse = {"left": _ReactivePulse(), "right": _ReactivePulse()}

    def from_envelope(
        self,
        *,
        input_state: ControllerInput,
        audio_envelope: float = 0.0,
        strength_percent: int = 45,
        now: float | None = None,
    ) -> TriggerState | None:
        current = self.clock() if now is None else float(now)
        level = max(0.0, min(1.0, float(audio_envelope)))
        strength = max(10, min(100, int(strength_percent))) / 100.0
        audio_rise = max(0.0, level - self._previous_audio)

        left = self._effect_for_side(
            "left",
            max(0.0, min(1.0, float(input_state.l2))),
            level=level,
            audio_rise=audio_rise,
            strength=strength,
            now=current,
        )
        right = self._effect_for_side(
            "right",
            max(0.0, min(1.0, float(input_state.r2))),
            level=level,
            audio_rise=audio_rise,
            strength=strength,
            now=current,
        )

        self._previous_audio = level
        self._previous_press["left"] = max(0.0, min(1.0, float(input_state.l2)))
        self._previous_press["right"] = max(0.0, min(1.0, float(input_state.r2)))

        if left.is_off and right.is_off:
            return None
        return TriggerState(left=left, right=right)

    def _effect_for_side(
        self,
        side: str,
        press: float,
        *,
        level: float,
        audio_rise: float,
        strength: float,
        now: float,
    ) -> AdaptiveTriggerEffect:
        previous = self._previous_press[side]

        if press <= self.PRESS_THRESHOLD:
            self._pulse[side] = _ReactivePulse()
            return AdaptiveTriggerEffect()

        crossed_engagement = previous < self.KICK_THRESHOLD <= press
        sharp_press = press - previous >= 0.22
        sharp_audio = audio_rise >= self.AUDIO_TRANSIENT_THRESHOLD and press >= self.KICK_THRESHOLD

        if crossed_engagement or sharp_press or sharp_audio:
            press_energy = min(1.0, max(press, (press - previous) * 2.5))
            audio_energy = min(1.0, audio_rise * 2.2)
            energy = max(0.18, press_energy, audio_energy)
            duration = self.KICK_SECONDS if crossed_engagement or sharp_press else self.AUDIO_PULSE_SECONDS
            frequency = max(6, min(30, round(8 + 20 * max(level, audio_energy))))
            self._pulse[side] = _ReactivePulse(
                until=now + duration,
                energy=energy,
                frequency=frequency,
            )

        pulse = self._pulse[side]
        if now < pulse.until:
            pulse_force = max(1, min(255, round(255 * strength * (0.30 + 0.70 * pulse.energy))))
            amplitude = max(1, min(255, round(255 * strength * (0.25 + 0.75 * pulse.energy))))
            return AdaptiveTriggerEffect(
                mode="pulse",
                start_position=42,
                end_position=205,
                force=pulse_force,
                frequency=pulse.frequency,
                amplitude=amplitude,
            )

        # Progressive resistance is intentionally soft in the first part of
        # travel. The pressure curve carries most of the weight; audio only
        # modulates a trigger that the player is already using.
        normalized = (press - self.PRESS_THRESHOLD) / (1.0 - self.PRESS_THRESHOLD)
        pressure_curve = max(0.0, min(1.0, normalized)) ** 1.65
        intensity = min(1.0, pressure_curve * (0.82 + 0.18 * level) + (0.08 * level * press))
        force = max(1, min(255, round(255 * strength * (0.10 + 0.90 * intensity))))

        # Moving the feedback start point through only a few firmware zones
        # gives a perceptible "bite" change without constantly rebuilding a
        # hard wall under the player's finger.
        start_position = round(92 - 34 * min(1.0, pressure_curve + 0.25 * level))
        return AdaptiveTriggerEffect(
            mode="resistance",
            start_position=max(48, min(96, start_position)),
            force=force,
        )
