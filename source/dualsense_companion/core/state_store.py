"""Thread-safe immutable runtime snapshot store."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from threading import RLock
from typing import Any

from ..domain.events import EventEnvelope, EventType
from ..domain.models import RuntimeSnapshot
from .event_bus import EventBus, Subscription


class StateStore:
    """Owns snapshots and publishes changes without exposing mutable state."""

    def __init__(self, initial: RuntimeSnapshot, *, event_bus: EventBus | None = None) -> None:
        self._snapshot = initial
        self._lock = RLock()
        self.events = event_bus or EventBus()

    def get(self) -> RuntimeSnapshot:
        with self._lock:
            return self._snapshot

    def update(self, **changes: Any) -> RuntimeSnapshot:
        with self._lock:
            current = self._snapshot
            next_snapshot = replace(
                current,
                **changes,
                sequence=current.sequence + 1,
                updated_at=time.time(),
            )
            self._snapshot = next_snapshot
        self.events.publish(
            EventEnvelope(
                EventType.STATE_UPDATED.value,
                {"state": next_snapshot.to_dict()},
            )
        )
        return next_snapshot

    def mutate(self, updater: Callable[[RuntimeSnapshot], RuntimeSnapshot]) -> RuntimeSnapshot:
        with self._lock:
            current = self._snapshot
            next_snapshot = updater(current)
            if not isinstance(next_snapshot, RuntimeSnapshot):
                raise TypeError("StateStore updater must return RuntimeSnapshot")
            next_snapshot = replace(
                next_snapshot,
                sequence=current.sequence + 1,
                updated_at=time.time(),
            )
            self._snapshot = next_snapshot
        self.events.publish(EventEnvelope(EventType.STATE_UPDATED.value, {"state": next_snapshot.to_dict()}))
        return next_snapshot

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.publish(EventEnvelope(event_type, payload))

    def subscribe(self, *, maxsize: int | None = None) -> Subscription:
        return self.events.subscribe(maxsize=maxsize)

    def unsubscribe(self, subscription: Subscription) -> None:
        self.events.unsubscribe(subscription)
