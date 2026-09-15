"""Compatibility exports for the upstream touch/mouse module name."""

from __future__ import annotations

from typing import Any

from .core.touchpad import GestureInterpreter, MouseAction, TouchpadService
from .platform.windows.mouse_output import (
    INPUT,
    MOUSEEVENTF_HWHEEL,
    MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP,
    MOUSEEVENTF_MOVE,
    MOUSEEVENTF_RIGHTDOWN,
    MOUSEEVENTF_RIGHTUP,
    MOUSEEVENTF_WHEEL,
    MOUSEINPUT,
    WindowsMouseOutput,
)

_output = WindowsMouseOutput()


def mouse_move(dx: int, dy: int) -> None:
    _output.move(dx, dy)


def mouse_button(left: bool, down: bool) -> None:
    _output.button(left, down)


def mouse_wheel(amount: int, horizontal: bool = False) -> None:
    _output.wheel(amount, horizontal=horizontal)


class TouchMouseEngine:
    """Small compatibility wrapper; new code uses ``TouchpadService``."""

    def __init__(self, state: Any) -> None:
        self.state = state
        self.service = TouchpadService(
            _output,
            lambda: dict(state.config),
            toggle_callback=state.toggle,
        )

    def start(self) -> None:
        # The new controller service feeds immutable input readings directly;
        # retaining a thread here would recreate the old shared-state design.
        return None

    def stop(self) -> None:
        self.service.reset()


__all__ = [
    "GestureInterpreter",
    "INPUT",
    "MOUSEINPUT",
    "MOUSEEVENTF_HWHEEL",
    "MOUSEEVENTF_LEFTDOWN",
    "MOUSEEVENTF_LEFTUP",
    "MOUSEEVENTF_MOVE",
    "MOUSEEVENTF_RIGHTDOWN",
    "MOUSEEVENTF_RIGHTUP",
    "MOUSEEVENTF_WHEEL",
    "MouseAction",
    "TouchMouseEngine",
    "TouchpadService",
    "mouse_button",
    "mouse_move",
    "mouse_wheel",
]
