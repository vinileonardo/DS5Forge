"""Small bounded event bus safe to publish from worker threads."""

from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Lock

from ..domain.events import EventEnvelope


@dataclass(frozen=True, slots=True)
class Subscription:
    """A queue-backed subscription owned by one API/UI consumer."""

    queue: Queue[EventEnvelope]

    def get(self, timeout: float | None = None) -> EventEnvelope:
        return self.queue.get(timeout=timeout)

    def get_nowait(self) -> EventEnvelope:
        return self.queue.get_nowait()


class EventBus:
    def __init__(self, *, default_queue_size: int = 64) -> None:
        self._default_queue_size = max(1, default_queue_size)
        self._lock = Lock()
        self._subscribers: set[Queue[EventEnvelope]] = set()

    def subscribe(self, *, maxsize: int | None = None) -> Subscription:
        queue: Queue[EventEnvelope] = Queue(maxsize=maxsize or self._default_queue_size)
        with self._lock:
            self._subscribers.add(queue)
        return Subscription(queue)

    def unsubscribe(self, subscription: Subscription) -> None:
        with self._lock:
            self._subscribers.discard(subscription.queue)

    def publish(self, event: EventEnvelope) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers)
        for queue in subscribers:
            self._put_latest(queue, event)

    @staticmethod
    def _put_latest(queue: Queue[EventEnvelope], event: EventEnvelope) -> None:
        try:
            queue.put_nowait(event)
            return
        except Full:
            # A noisy telemetry stream must not block the controller worker.
            # Keep the newest event and discard the oldest queued item. If a
            # consumer freed the slot between Full and get_nowait(), still try
            # to enqueue the newest event instead of dropping it unnecessarily.
            try:
                queue.get_nowait()
            except Empty:
                pass
            try:
                queue.put_nowait(event)
            except Full:
                pass
