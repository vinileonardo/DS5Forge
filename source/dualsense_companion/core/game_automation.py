"""Foreground polling and pure game-rule evaluation."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Sequence

from ..diagnostics.logging import get_logger
from ..domain.errors import DS5ForgeError, ErrorCode
from ..domain.games import (
    ConflictDiagnostic,
    ForegroundApplication,
    GameDefinition,
    GameMatch,
    RuleEvaluation,
)
from .ports import ForegroundDetector, ProcessInspector

LOGGER = get_logger(__name__)


def evaluate_game_rules(
    foreground: ForegroundApplication,
    games: Sequence[GameDefinition],
) -> tuple[GameMatch | None, tuple[RuleEvaluation, ...]]:
    """Evaluate every rule in registry order and explain every result."""

    match: GameMatch | None = None
    evaluations: list[RuleEvaluation] = []
    for game in games:
        candidate = game.matches(foreground)
        is_selected = candidate.matched and match is None
        if is_selected:
            match = candidate
        evaluations.append(
            RuleEvaluation(
                game_id=game.id,
                game_name=game.name,
                matched=candidate.matched,
                reason=candidate.reason,
                action="activate" if is_selected else "none",
                profile=game.profile if candidate.matched else None,
                compatibility_mode=game.compatibility_mode if candidate.matched else None,
            )
        )
    return match, tuple(evaluations)


class ForegroundWorker:
    """Bounded, interruptible 500 ms–1 s foreground polling worker."""

    def __init__(
        self,
        detector: ForegroundDetector,
        on_observation: Callable[[ForegroundApplication, bool], None],
        *,
        on_error: Callable[[DS5ForgeError], None] | None = None,
        interval: float = 0.75,
    ) -> None:
        self.detector = detector
        self.on_observation = on_observation
        self.on_error = on_error
        self.interval = max(0.5, min(1.0, float(interval)))
        self.stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_context: tuple[object, ...] | None = None

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.alive:
            return
        self.stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="DS5ForgeForeground", daemon=False)
        self._thread.start()

    def stop(self, *, join_timeout: float = 2.0) -> None:
        self.stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=join_timeout)
        if self.alive:
            LOGGER.error("foreground worker did not stop before timeout", extra={"event": "foreground.stop_timeout"})
        else:
            # A fresh start must re-evaluate the current context instead of
            # treating the first observation after restart as unchanged.
            self._last_context = None

    def poll_once(self) -> ForegroundApplication:
        try:
            observation = self.detector.current()
            if not isinstance(observation, ForegroundApplication):
                raise TypeError("foreground detector returned an invalid observation")
        except Exception as exc:
            error = (
                exc
                if isinstance(exc, DS5ForgeError)
                else DS5ForgeError(
                    ErrorCode.FOREGROUND_UNAVAILABLE,
                    "Foreground process inspection is unavailable.",
                    detail=str(exc),
                )
            )
            if self.on_error:
                self.on_error(error)
            observation = ForegroundApplication.desktop(now=time.time(), diagnostic=error.message)
        changed = self._last_context != observation.context_key
        self._last_context = observation.context_key
        self.on_observation(observation, changed)
        return observation

    def _run(self) -> None:
        while not self.stop_event.is_set():
            self.poll_once()
            self.stop_event.wait(self.interval)


def conflict_diagnostics(
    process_names: Iterable[str],
    inspector: ProcessInspector | None,
    *,
    now: float | None = None,
) -> tuple[ConflictDiagnostic, ...]:
    """Return honest best-effort diagnostics without controlling other apps."""

    checked_at = time.time() if now is None else now
    names = tuple(dict.fromkeys(str(name) for name in process_names))
    running: set[str] | None = None
    evidence: str | None = None
    if inspector is not None:
        try:
            observed = inspector.running_processes()
            if observed is None:
                evidence = "Process inspection is unavailable in this environment."
            else:
                running = {name.casefold() for name in observed}
        except Exception as exc:
            evidence = f"Process inspection failed: {exc}"
    else:
        evidence = "Process inspection adapter is unavailable in this environment."

    result: list[ConflictDiagnostic] = []
    for process in names:
        is_running = bool(running is not None and process.casefold() in running)
        lower = process.casefold()
        if running is None:
            severity = "info"
            message = f"Could not inspect whether {process} is running."
            item_evidence = evidence
        elif is_running and lower == "steam.exe":
            severity = "warning"
            message = "Steam is running. Steam Input may affect this game depending on its configuration."
            item_evidence = "Process name was observed; Steam Input activity was not proven."
        elif is_running:
            severity = "warning"
            message = f"{process} is running and may remap or virtualize controller input."
            item_evidence = "Process name was observed; active input interception was not proven."
        else:
            severity = "info"
            message = f"{process} was not detected."
            item_evidence = "Process-name check only."
        result.append(
            ConflictDiagnostic(
                process=process,
                running=is_running,
                severity=severity,
                message=message,
                evidence=item_evidence,
                checked_at=checked_at,
            )
        )
    return tuple(result)
