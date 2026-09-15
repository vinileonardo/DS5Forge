"""Bounded, single-flight safety coordinators for Controller Lab outputs."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from ..diagnostics.logging import get_logger
from ..domain.errors import DS5ForgeError, ErrorCode
from ..domain.models import (
    HapticsTestRun,
    TriggerPreviewState,
    TriggerState,
)

LOGGER = get_logger(__name__)


class TriggerPreviewCoordinator:
    """Apply a trigger preview and guarantee an eventual Off reset."""

    def __init__(
        self,
        apply_effect: Callable[[TriggerState], None],
        reset_effect: Callable[[], None],
        *,
        on_state: Callable[[TriggerPreviewState], None] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.apply_effect = apply_effect
        self.reset_effect = reset_effect
        self.on_state = on_state
        self.clock = clock
        self._lock = threading.RLock()
        self._timer: threading.Timer | None = None
        self._state: TriggerPreviewState | None = None

    @property
    def state(self) -> TriggerPreviewState | None:
        with self._lock:
            return self._state

    def start(self, effect: TriggerState, *, duration_ms: int = 1_000) -> TriggerPreviewState:
        if not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or not 10 <= duration_ms <= 5_000:
            raise DS5ForgeError(
                ErrorCode.API_VALIDATION,
                "Trigger preview duration is invalid.",
                fields={"duration_ms": "must be an integer between 10 and 5000"},
            )
        with self._lock:
            if self._state is not None and self._state.active:
                raise DS5ForgeError(
                    ErrorCode.TRIGGER_PREVIEW_BUSY,
                    "A trigger preview is already running.",
                    fields={"preview": "cancel or wait for the current preview"},
                )
            self._cancel_timer_locked()
            started = self.clock()
            preview = TriggerPreviewState(
                id=uuid.uuid4().hex,
                status="running",
                started_at=started,
                expires_at=started + duration_ms / 1000.0,
            )
            try:
                self.apply_effect(effect)
            except DS5ForgeError:
                self._safe_reset()
                raise
            except Exception as exc:
                self._safe_reset()
                raise DS5ForgeError(
                    ErrorCode.TRIGGER_OUTPUT_FAILED,
                    "Trigger preview could not be applied.",
                    detail=str(exc),
                ) from exc
            self._state = preview
            self._timer = threading.Timer(duration_ms / 1000.0, self._timeout, args=(preview.id,))
            self._timer.daemon = True
            self._timer.start()
        self._notify(preview)
        return preview

    def cancel(self) -> TriggerPreviewState | None:
        with self._lock:
            current = self._state
            if current is None or not current.active:
                return current
            self._cancel_timer_locked()
            reset_error = self._safe_reset()
            next_state = replace(
                current,
                status="error" if reset_error else "cancelled",
                expires_at=self.clock(),
                error=reset_error.to_snapshot() if reset_error else None,
            )
            self._state = next_state
        self._notify(next_state)
        if reset_error:
            raise reset_error
        return next_state

    def reset(self, *, status: str = "reset") -> TriggerPreviewState | None:
        """Cancel any timer, neutralize both triggers and mark the preview."""

        with self._lock:
            current = self._state
            self._cancel_timer_locked()
            reset_error = self._safe_reset()
            if current is None:
                if reset_error:
                    LOGGER.error(
                        "trigger preview safety reset failed without active preview",
                        extra={"event": "controller.trigger_reset"},
                    )
                return None
            next_state = replace(
                current,
                status="error" if reset_error else status,
                expires_at=self.clock(),
                error=reset_error.to_snapshot() if reset_error else None,
            )
            self._state = next_state
        self._notify(next_state)
        if reset_error:
            raise reset_error
        return next_state

    def _timeout(self, preview_id: str) -> None:
        with self._lock:
            current = self._state
            if current is None or current.id != preview_id or not current.active:
                return
            self._timer = None
            reset_error = self._safe_reset()
            next_state = replace(
                current,
                status="error" if reset_error else "timed_out",
                expires_at=self.clock(),
                error=reset_error.to_snapshot() if reset_error else None,
            )
            self._state = next_state
        self._notify(next_state)

    def _cancel_timer_locked(self) -> None:
        timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()

    def _safe_reset(self) -> DS5ForgeError | None:
        try:
            self.reset_effect()
        except DS5ForgeError as exc:
            LOGGER.error("trigger preview neutralization failed", extra={"event": "controller.trigger_reset"})
            return exc
        except Exception as exc:
            LOGGER.exception("trigger preview neutralization failed", extra={"event": "controller.trigger_reset"})
            return DS5ForgeError(
                ErrorCode.TRIGGER_OUTPUT_FAILED,
                "Adaptive triggers could not be neutralized after the preview.",
                detail=str(exc),
            )
        return None

    def _notify(self, state: TriggerPreviewState) -> None:
        if self.on_state is not None:
            self.on_state(state)


class HapticsTestBench:
    """Bounded single-flight rumble bench with mandatory neutralization."""

    def __init__(
        self,
        output: Callable[[int, int], Any],
        neutralize: Callable[[], Any],
        *,
        on_state: Callable[[HapticsTestRun], None] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.output = output
        self.neutralize = neutralize
        self.on_state = on_state
        self.clock = clock
        self._lock = threading.RLock()
        self._timer: threading.Timer | None = None
        self._run: HapticsTestRun | None = None

    @property
    def run(self) -> HapticsTestRun | None:
        with self._lock:
            return self._run

    def start(self, *, left: int = 200, right: int = 160, duration_ms: int = 350) -> HapticsTestRun:
        self._validate(left, right, duration_ms)
        with self._lock:
            if self._run is not None and self._run.status == "running":
                raise DS5ForgeError(
                    ErrorCode.HAPTICS_TEST_BUSY,
                    "A haptics test is already running.",
                    fields={"test": "cancel or wait for the current test"},
                )
            self._cancel_timer_locked()
            started = self.clock()
            run = HapticsTestRun(
                id=uuid.uuid4().hex,
                status="running",
                left=left,
                right=right,
                duration_ms=duration_ms,
                started_at=started,
                expires_at=started + duration_ms / 1000.0,
            )
            try:
                accepted = self.output(left, right)
                if accepted is False:
                    raise DS5ForgeError(
                        ErrorCode.HAPTICS_TEST_FAILED,
                        "The controller did not accept the haptics test.",
                    )
            except DS5ForgeError:
                self._safe_neutralize()
                raise
            except Exception as exc:
                self._safe_neutralize()
                raise DS5ForgeError(
                    ErrorCode.HAPTICS_TEST_FAILED,
                    "The haptics test could not start.",
                    detail=str(exc),
                ) from exc
            self._run = run
            self._timer = threading.Timer(duration_ms / 1000.0, self._finish, args=(run.id,))
            self._timer.daemon = True
            self._timer.start()
        self._notify(run)
        return run

    def cancel(self) -> HapticsTestRun | None:
        with self._lock:
            current = self._run
            if current is None or current.status != "running":
                return current
            self._cancel_timer_locked()
            neutralize_error = self._safe_neutralize()
            next_run = replace(current, status="cancelled", expires_at=self.clock())
            if neutralize_error:
                next_run = replace(next_run, status="error", error=neutralize_error.to_snapshot())
            self._run = next_run
        self._notify(next_run)
        if neutralize_error:
            raise neutralize_error
        return next_run

    def stop(self) -> None:
        try:
            self.cancel()
        except DS5ForgeError:
            LOGGER.error("haptics stop could not neutralize the active run", extra={"event": "haptics.stop"})
        self._safe_neutralize()

    def _finish(self, run_id: str) -> None:
        with self._lock:
            current = self._run
            if current is None or current.id != run_id or current.status != "running":
                return
            self._timer = None
            neutralize_error = self._safe_neutralize()
            next_run = replace(
                current,
                status="error" if neutralize_error else "completed",
                expires_at=self.clock(),
                error=neutralize_error.to_snapshot() if neutralize_error else None,
            )
            self._run = next_run
        self._notify(next_run)

    def _cancel_timer_locked(self) -> None:
        timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()

    def _safe_neutralize(self) -> DS5ForgeError | None:
        try:
            self.neutralize()
        except DS5ForgeError as exc:
            LOGGER.error("haptics neutralization failed", extra={"event": "haptics.neutralize"})
            return exc
        except Exception as exc:
            LOGGER.exception("haptics neutralization failed", extra={"event": "haptics.neutralize"})
            return DS5ForgeError(
                ErrorCode.HAPTICS_TEST_FAILED,
                "Haptics output could not be neutralized.",
                detail=str(exc),
            )
        return None

    def _notify(self, run: HapticsTestRun) -> None:
        if self.on_state is not None:
            self.on_state(run)

    @staticmethod
    def _validate(left: int, right: int, duration_ms: int) -> None:
        if any(not isinstance(value, int) or isinstance(value, bool) for value in (left, right)):
            raise DS5ForgeError(ErrorCode.API_VALIDATION, "Haptics intensity must be an integer.")
        if not 0 <= left <= 255 or not 0 <= right <= 255:
            raise DS5ForgeError(
                ErrorCode.API_VALIDATION,
                "Haptics intensity is outside the supported range.",
                fields={"left": "0..255", "right": "0..255"},
            )
        if not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or not 10 <= duration_ms <= 5_000:
            raise DS5ForgeError(
                ErrorCode.API_VALIDATION,
                "Haptics test duration is outside the supported range.",
                fields={"duration_ms": "10..5000 milliseconds"},
            )
