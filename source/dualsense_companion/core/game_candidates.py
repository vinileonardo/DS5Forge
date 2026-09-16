"""Running/recent game candidates for the Games picker."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class GameCandidate:
    executable_name: str
    executable_path: str | None = None
    pid: int | None = None
    title: str | None = None
    source: str = "recent"
    observed_at: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "executable_name": self.executable_name,
            "executable_path": self.executable_path,
            "pid": self.pid,
            "title": self.title,
            "source": self.source,
            "observed_at": self.observed_at,
        }


class GameCandidateProvider(Protocol):
    def running(self) -> Iterable[GameCandidate]: ...

    def recent(self) -> Iterable[GameCandidate]: ...


def merge_candidates(
    running: Iterable[GameCandidate],
    recent: Iterable[GameCandidate],
    *,
    limit: int = 64,
) -> list[GameCandidate]:
    """Deduplicate by case-insensitive path/name while preferring running."""

    result: list[GameCandidate] = []
    seen: set[tuple[str, str]] = set()
    for candidate in [*running, *recent]:
        key = ((candidate.executable_path or "").casefold(), candidate.executable_name.casefold())
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
        if len(result) >= max(1, int(limit)):
            break
    return result


class FakeGameCandidateProvider:
    def __init__(self, running: Iterable[GameCandidate] = (), recent: Iterable[GameCandidate] = ()) -> None:
        self._running = tuple(running)
        self._recent = tuple(recent)

    def running(self) -> tuple[GameCandidate, ...]:
        return self._running

    def recent(self) -> tuple[GameCandidate, ...]:
        return self._recent
