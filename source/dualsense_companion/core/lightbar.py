"""Interruptible lightbar animation and software intensity scaling."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from ..domain.models import LightbarState


def scale_rgb(state: LightbarState) -> tuple[int, int, int]:
    """Return the visible RGB after software intensity scaling."""

    if not state.enabled:
        return 0, 0, 0
    intensity = max(0.0, min(1.0, float(state.intensity)))
    return tuple(max(0, min(255, round(channel * intensity))) for channel in (state.r, state.g, state.b))  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class PulseFrame:
    state: LightbarState
    index: int
    total: int


class InterruptiblePulseAnimator:
    """One replaceable worker; stop/join always prevents stale writes."""

    def __init__(self, apply: Callable[[LightbarState], None], *, interval: float = 0.08) -> None:
        self.apply = apply
        self.interval = max(0.01, float(interval))
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, state: LightbarState, *, cycles: int = 2) -> None:
        self.stop()
        if state.effect not in {"pulse", "slow", "fast"} and state.pulse == "off":
            self.apply(state)
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(state, max(1, int(cycles))),
            name="DS5ForgeLightbarPulse",
            daemon=False,
        )
        self._thread.start()

    def stop(self, *, reset: LightbarState | None = None, join_timeout: float = 1.0) -> None:
        with self._lock:
            self._stop.set()
            thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=join_timeout)
        if reset is not None:
            self.apply(reset)

    def _run(self, state: LightbarState, cycles: int) -> None:
        total = cycles * 2
        for index in range(total):
            if self._stop.is_set():
                return
            phase = 0.35 + 0.65 * ((index % 2) == 0)
            self.apply(
                LightbarState(
                    r=state.r,
                    g=state.g,
                    b=state.b,
                    enabled=state.enabled,
                    intensity=state.intensity * phase,
                    effect=state.effect,
                    brightness=state.brightness,
                    pulse=state.pulse,
                )
            )
            if self._stop.wait(self.interval):
                return
        if not self._stop.is_set():
            self.apply(state)

    def close(self) -> None:
        self.stop(reset=LightbarState())
