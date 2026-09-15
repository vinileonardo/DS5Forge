"""Bounded controller telemetry decimation and latest-value transport."""

from __future__ import annotations

import time
from collections.abc import Callable
from math import inf
from queue import Empty, Full, Queue
from threading import Lock
from typing import TypeVar

from ..domain.models import ControllerInput, ControllerTelemetry, normalize_controller_input

T = TypeVar("T")


class BoundedLatestQueue[T]:
    """A bounded queue that always prefers the newest value.

    It is deliberately small and has no history or blocking producer path.
    This is useful for telemetry consumers that should render the current
    state, not replay every hardware sample.
    """

    def __init__(self, maxsize: int = 1) -> None:
        self.maxsize = max(1, int(maxsize))
        self._queue: Queue[T] = Queue(maxsize=self.maxsize)

    def put_latest(self, value: T) -> None:
        try:
            self._queue.put_nowait(value)
            return
        except Full:
            try:
                self._queue.get_nowait()
            except Empty:
                pass
            try:
                self._queue.put_nowait(value)
            except Full:
                # A concurrent consumer won the slot. Dropping this sample is
                # safe because a subsequent hardware sample will supersede it.
                return

    def get(self, timeout: float | None = None) -> T:
        return self._queue.get(timeout=timeout)

    def get_nowait(self) -> T:
        return self._queue.get_nowait()

    def qsize(self) -> int:
        return self._queue.qsize()


class TelemetryPublisher:
    """Decimate approximately 250 Hz reads to a bounded 30 Hz stream.

    ``offer`` stores only the newest un-published input. The callback runs
    outside the lock and is invoked at most once per configured interval.
    """

    def __init__(
        self,
        *,
        max_hz: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        on_publish: Callable[[ControllerTelemetry], None] | None = None,
    ) -> None:
        if max_hz <= 0 or not inf > max_hz:
            raise ValueError("max_hz must be finite and greater than zero")
        self.max_hz = float(max_hz)
        self.interval = 1.0 / self.max_hz
        self.clock = clock
        self.on_publish = on_publish
        self._lock = Lock()
        self._latest: ControllerInput | None = None
        self._last_published_at: float | None = None
        self._sequence = 0

    @property
    def latest(self) -> ControllerInput | None:
        with self._lock:
            return self._latest

    @property
    def sequence(self) -> int:
        with self._lock:
            return self._sequence

    def reset(self, *, keep_sequence: bool = True) -> None:
        """Drop the held sample at a disconnect/reconnect boundary.

        Sequence numbers remain monotonic by default so clients can detect
        reconnects without confusing a new sample for an older one.
        """

        with self._lock:
            self._latest = None
            self._last_published_at = None
            if not keep_sequence:
                self._sequence = 0

    def offer(self, sample: ControllerInput, *, timestamp: float | None = None) -> ControllerTelemetry | None:
        normalized = normalize_controller_input(sample)
        now = self.clock() if timestamp is None else float(timestamp)
        with self._lock:
            self._latest = normalized
            if self._last_published_at is not None and now - self._last_published_at < self.interval:
                return None
            self._last_published_at = now
            self._sequence += 1
            telemetry = ControllerTelemetry(
                input=normalized,
                sequence=self._sequence,
                timestamp=now,
                sample_rate_hz=self.max_hz,
            )
        if self.on_publish is not None:
            self.on_publish(telemetry)
        return telemetry

    def flush(self, *, timestamp: float | None = None) -> ControllerTelemetry | None:
        """Publish the newest held sample when its interval has elapsed."""

        with self._lock:
            latest = self._latest
        return self.offer(latest, timestamp=timestamp) if latest is not None else None


# Names used by integrations and tests that describe the same contract.
TelemetryDecimator = TelemetryPublisher
LatestValuePublisher = TelemetryPublisher
