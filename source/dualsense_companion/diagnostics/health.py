"""Health projection kept separate from the HTTP presentation layer."""

from __future__ import annotations

from dataclasses import replace

from ..domain.models import HealthSnapshot, RuntimeSnapshot


def health_from_snapshot(snapshot: RuntimeSnapshot) -> HealthSnapshot:
    """Return the health contract consumers should use for readiness decisions."""

    if snapshot.connection.value == "stopping":
        return replace(snapshot.health, process_alive=False, controller_available=False)
    return snapshot.health
