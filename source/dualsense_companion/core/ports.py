"""Protocols between platform adapters and the platform-neutral core."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Protocol

from ..domain.models import (
    ControllerCapabilities,
    ControllerIdentity,
    ControllerReading,
)


class ControllerAdapter(Protocol):
    identity: ControllerIdentity
    capabilities: ControllerCapabilities

    def is_connected(self) -> bool: ...

    def read(self) -> ControllerReading: ...

    def set_motors(self, left: int, right: int) -> None: ...

    def neutralize(self) -> None: ...

    def startup_feedback(self) -> None: ...

    def close(self) -> None: ...


class ControllerFactory(Protocol):
    def connect(self) -> ControllerAdapter: ...


class MouseOutput(Protocol):
    def move(self, dx: int, dy: int) -> None: ...

    def button(self, left: bool, down: bool) -> None: ...

    def wheel(self, amount: int, horizontal: bool = False) -> None: ...

    def release_all(self) -> None: ...


class AudioCapture(Protocol):
    sample_rate: int
    channels: int
    frames: int
    name: str

    def read(self) -> bytes: ...

    def default_output_changed(self) -> bool: ...

    def close(self) -> None: ...


class AudioCaptureFactory(Protocol):
    def open(self) -> AbstractContextManager[AudioCapture]: ...


ErrorCallback = Callable[[Exception], None]
