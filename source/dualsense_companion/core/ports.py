"""Protocols between platform adapters and the platform-neutral core."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Protocol

from ..domain.games import ForegroundApplication, VirtualControllerCapability
from ..domain.input_isolation import InputIsolationCapability, InputIsolationStatus
from ..domain.models import (
    BatterySnapshot,
    ControllerCapabilities,
    ControllerIdentity,
    ControllerInput,
    ControllerReading,
    LightbarState,
    PlayerLedState,
    TriggerState,
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


class ControllerLabAdapter(Protocol):
    """Optional output surface exposed by a platform controller adapter."""

    def get_lightbar(self) -> LightbarState: ...

    def set_lightbar(self, state: LightbarState) -> None: ...

    def reset_lightbar(self) -> None: ...

    def get_player_leds(self) -> PlayerLedState: ...

    def set_player_leds(self, state: PlayerLedState) -> None: ...

    def reset_player_leds(self) -> None: ...

    def set_triggers(self, state: TriggerState) -> None: ...

    def reset_triggers(self) -> None: ...


class ControllerFactory(Protocol):
    def connect(self) -> ControllerAdapter: ...


class MouseOutput(Protocol):
    def move(self, dx: int, dy: int) -> None: ...

    def button(self, left: bool, down: bool) -> None: ...

    def wheel(self, amount: int, horizontal: bool = False) -> None: ...

    def release_all(self) -> None: ...


class KeyboardOutput(Protocol):
    """Small platform boundary for keyboard SendInput ownership."""

    def key(self, code: str, down: bool) -> None: ...

    def release_all(self) -> None: ...


class ForegroundDetector(Protocol):
    def current(self) -> ForegroundApplication: ...


class ProcessInspector(Protocol):
    def running_processes(self) -> set[str] | None: ...


class VirtualControllerProvider(Protocol):
    def capability(self) -> VirtualControllerCapability: ...

    def start(self) -> None: ...

    def send_button(self, code: str, down: bool) -> None: ...

    def release_all(self) -> None: ...

    def close(self) -> None: ...


class ExclusiveVirtualCapability(Protocol):
    """Provider probe used by the Exclusive coordinator.

    The concrete Windows helper may expose a richer object; keeping the
    protocol structural prevents the core from importing HIDMaestro/.NET.
    """

    available: bool
    installed: bool
    output_reports: bool
    provenance: object
    reason: str | None


class PhysicalOutputReportSink(Protocol):
    """Physical DualSense output path used while Exclusive owns the device.

    Entering passthrough must stop DS5Forge-generated output reports from
    racing the game's virtual-controller feedback. Implementations restore
    their normal output loop when the Exclusive session ends.
    """

    def capability(self) -> object: ...

    def begin(self, *, token: str, generation: int) -> None: ...

    def submit(self, report: bytes, *, token: str, generation: int) -> None: ...

    def end(self, *, token: str, generation: int) -> None: ...


class PhysicalInputSuppressionProvider(Protocol):
    """Session-scoped physical input suppression (HidHide adapter boundary)."""

    def capability(self) -> object: ...

    def enable(self, *, token: str, generation: int) -> None: ...

    def heartbeat(self, *, token: str, generation: int) -> None: ...

    def disable(self, *, token: str, generation: int) -> None: ...

    def recover_stale(self) -> None: ...


class PhysicalInputIsolationProvider(Protocol):
    """Explicit physical-device isolation used by Remap anti-double-input."""

    def capability(self) -> InputIsolationCapability: ...

    def status(self) -> InputIsolationStatus: ...

    def enable(self) -> InputIsolationStatus: ...

    def disable(self) -> InputIsolationStatus: ...

    def recover_stale(self) -> bool: ...


class VirtualOutputReportSource(Protocol):
    """Full DualSense state sink used by Exclusive mirroring."""

    def capability(self) -> object: ...

    def start(self, *, token: str, generation: int) -> None: ...

    def heartbeat(self, *, token: str, generation: int) -> None: ...

    def submit_state(
        self,
        input_state: ControllerInput,
        *,
        battery: BatterySnapshot,
        sequence: int,
        token: str,
        generation: int,
    ) -> tuple[bytes, ...] | None: ...

    def close(self, *, token: str, generation: int) -> None: ...

    def recover_stale(self) -> None: ...


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
