"""Legacy state projection; hardware ownership moved to ``CoreFacade``."""

from __future__ import annotations

from typing import Any


class AppState:
    """Read-only compatibility projection for integrations using the baseline.

    It deliberately does not expose ``ds`` or mutable controller state. New
    code should use ``CoreFacade.snapshot()`` and its command methods.
    """

    def __init__(self, facade: Any) -> None:
        if not hasattr(facade, "snapshot"):
            raise TypeError("AppState requires a CoreFacade")
        self.facade = facade

    @property
    def config(self) -> dict[str, Any]:
        return self.facade.config()

    @property
    def rumble_enabled(self) -> bool:
        return self.facade.snapshot().rumble_enabled

    @property
    def trackpad_enabled(self) -> bool:
        return self.facade.snapshot().touchpad_enabled

    @property
    def controller_connected(self) -> bool:
        return self.facade.snapshot().connection.value == "connected"

    @property
    def battery(self) -> int:
        return self.facade.snapshot().battery.level

    @property
    def motor_left(self) -> int:
        return self.facade.snapshot().motors.left

    @property
    def motor_right(self) -> int:
        return self.facade.snapshot().motors.right

    @property
    def listening_on(self) -> str:
        return self.facade.snapshot().audio.device or ""

    def toggle(self, target: str) -> None:
        self.facade.toggle(target)
