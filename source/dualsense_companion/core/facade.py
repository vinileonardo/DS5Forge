"""The only public runtime surface shared by GUI and local API."""

from __future__ import annotations

import copy
import threading
import time
from dataclasses import replace
from typing import Any

from ..diagnostics.health import health_from_snapshot
from ..diagnostics.logging import get_logger
from ..domain.errors import ConfigValidationError, DS5ForgeError, ErrorCode
from ..domain.events import EventType
from ..domain.models import (
    AudioSnapshot,
    ConnectionState,
    HealthSnapshot,
    MotorSnapshot,
    RuntimeSnapshot,
)
from .config import ConfigRepository, merge_config, validate_config
from .controller_service import ControllerService, LifecycleNotification
from .event_bus import Subscription
from .haptics_service import HapticsService
from .ports import AudioCaptureFactory, ControllerAdapter, ControllerFactory, MouseOutput
from .state_store import StateStore
from .touchpad import TouchpadService

LOGGER = get_logger(__name__)
RUMBLE_REBUILD_KEYS = frozenset(
    {
        "heavy_cutoff_hz",
        "texture_center_hz",
        "fast_attack_ms",
        "fast_release_ms",
        "baseline_attack_ms",
        "baseline_release_ms",
    }
)


class CoreFacade:
    """Coordinates core services without leaking hardware objects to clients."""

    def __init__(
        self,
        *,
        controller_factory: ControllerFactory,
        mouse_output: MouseOutput,
        capture_factory: AudioCaptureFactory | None = None,
        config_repository: ConfigRepository | None = None,
    ) -> None:
        self.config_repository = config_repository or ConfigRepository.default()
        self._config_lock = threading.RLock()
        self._config = self.config_repository.load()
        self._capture_factory = capture_factory
        self._reload_audio = threading.Event()
        self._haptics: HapticsService | None = None
        self._started = False
        self._stop_lock = threading.Lock()

        initial_error = self.config_repository.last_error.to_snapshot() if self.config_repository.last_error else None
        health = HealthSnapshot(
            process_alive=True,
            controller_available=False,
            subsystems={"core": "ready", "controller": "waiting", "audio": "stopped", "touchpad": "ready"},
            degraded=("config",) if initial_error else (),
        )
        initial = RuntimeSnapshot.initial(
            touchpad_enabled=bool(self._config["trackpad"].get("trackpad_enabled_on_start", True)),
            now=time.time(),
        )
        initial = replace(initial, health=health, last_error=initial_error)
        self.store = StateStore(initial)

        self._mouse_output = mouse_output
        self.touchpad = TouchpadService(
            self._mouse_output,
            self.config,
            toggle_callback=self.toggle,
            error_callback=self._on_touch_error,
        )
        self.controller = ControllerService(
            controller_factory,
            on_lifecycle=self._on_lifecycle,
            on_connected=self._on_connected,
            on_disconnected=self._on_disconnected,
            on_reading=self._on_reading,
            on_motors=self._on_motors,
        )

    def start(self) -> None:
        with self._stop_lock:
            if self._started:
                return
            self._started = True
        LOGGER.info("core starting", extra={"event": "core.start"})
        self.store.mutate(
            lambda current: replace(
                current,
                health=replace(
                    current.health,
                    process_alive=True,
                    controller_available=False,
                    subsystems={
                        **current.health.subsystems,
                        "core": "ready",
                        "controller": "waiting",
                        "audio": "stopped",
                        "touchpad": "ready",
                    },
                ),
            )
        )
        self.store.publish(EventType.DIAGNOSTIC.value, {"event": "core.started"})
        self.controller.start()

    def stop(self) -> None:
        with self._stop_lock:
            if not self._started:
                self.touchpad.reset()
                current = self.snapshot()
                self.store.update(
                    connection=ConnectionState.DISCONNECTED,
                    health=HealthSnapshot(
                        process_alive=False,
                        controller_available=False,
                        subsystems={
                            **current.health.subsystems,
                            "core": "stopped",
                            "controller": "stopped",
                            "touchpad": "stopped",
                        },
                        degraded=current.health.degraded,
                    ),
                )
                return
            self._started = False
        LOGGER.info("core stopping", extra={"event": "core.stop"})
        self.controller.stop()
        self._stop_haptics()
        self.touchpad.reset()
        self.store.update(
            connection=ConnectionState.DISCONNECTED,
            motors=MotorSnapshot(),
            health=HealthSnapshot(
                process_alive=False,
                controller_available=False,
                subsystems={"core": "stopped", "controller": "stopped", "audio": "stopped", "touchpad": "stopped"},
                degraded=(),
            ),
        )
        self.store.publish(EventType.DIAGNOSTIC.value, {"event": "core.stopped"})

    def snapshot(self) -> RuntimeSnapshot:
        return self.store.get()

    def state_dict(self) -> dict[str, Any]:
        return self.snapshot().to_dict()

    def health_dict(self) -> dict[str, Any]:
        return health_from_snapshot(self.snapshot()).to_dict()

    def config(self) -> dict[str, Any]:
        with self._config_lock:
            return copy.deepcopy(self._config)

    def save_config(self) -> dict[str, Any]:
        with self._config_lock:
            self._config = self.config_repository.save(self._config)
            result = copy.deepcopy(self._config)
        self._clear_config_degraded()
        self.store.publish(EventType.CONFIG.value, {"config": result})
        return result

    def update_config(
        self, patch: dict[str, Any], *, replace_all: bool = False, persist: bool = True
    ) -> dict[str, Any]:
        if not isinstance(patch, dict):
            raise ConfigValidationError(fields={"config": "must be an object"})
        with self._config_lock:
            candidate = copy.deepcopy(patch) if replace_all else merge_config(self._config, patch)
            normalized = validate_config(candidate)
            if persist:
                normalized = self.config_repository.save(normalized)
            self._config = normalized
            result = copy.deepcopy(normalized)
        rumble_patch = patch.get("rumble")
        if replace_all or (isinstance(rumble_patch, dict) and bool(RUMBLE_REBUILD_KEYS.intersection(rumble_patch))):
            self._reload_audio.set()
        self.store.update(config_version=int(result["schema_version"]))
        if persist:
            self._clear_config_degraded()
        self.store.publish(EventType.CONFIG.value, {"config": result})
        return result

    def set_rumble_enabled(self, enabled: bool) -> RuntimeSnapshot:
        enabled = bool(enabled)
        snapshot = self.store.update(rumble_enabled=enabled)
        if not enabled:
            self.controller.neutralize()
            snapshot = self.store.update(motors=MotorSnapshot())
        return snapshot

    def set_touchpad_enabled(self, enabled: bool) -> RuntimeSnapshot:
        enabled = bool(enabled)
        self.touchpad.set_enabled(enabled)
        return self.store.update(touchpad_enabled=enabled)

    def toggle(self, target: str) -> None:
        target = str(target)
        current = self.snapshot()
        if target == "rumble":
            self.set_rumble_enabled(not current.rumble_enabled)
        elif target == "trackpad":
            self.set_touchpad_enabled(not current.touchpad_enabled)
        elif target == "master":
            enabled = not (current.rumble_enabled or current.touchpad_enabled)
            self.set_rumble_enabled(enabled)
            self.set_touchpad_enabled(enabled)
        else:
            raise ConfigValidationError(fields={"mic_button": "unsupported target"})
        # Preserve the upstream microphone-toggle feedback on the right motor.
        self.controller.pulse(0, 140, 0.12)

    def test_rumble(self, *, left: int = 200, right: int = 160, duration_ms: int = 350) -> bool:
        if not 0 <= int(left) <= 255 or not 0 <= int(right) <= 255:
            raise ConfigValidationError(fields={"motors": "values must be between 0 and 255"})
        if not 10 <= int(duration_ms) <= 5_000:
            raise ConfigValidationError(fields={"duration_ms": "must be between 10 and 5000"})
        return self.controller.pulse(int(left), int(right), int(duration_ms) / 1000)

    def profiles(self) -> list[dict[str, Any]]:
        return self.config_repository.list_profiles()

    def load_profile(self, name: str) -> dict[str, Any]:
        profile = self.config_repository.load_profile(name)
        config = self.update_config({"rumble": profile}, persist=False)
        self.store.update(active_profile=name)
        self.store.publish(EventType.PROFILE.value, {"name": name, "source": "applied", "config": config})
        return config

    def save_profile(self, name: str, profile: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._config_lock:
            payload = profile if profile is not None else copy.deepcopy(self._config["rumble"])
        saved = self.config_repository.save_profile(name, payload)
        self.store.publish(EventType.PROFILE.value, {"name": name, "source": "user", "saved": True})
        return saved

    def delete_profile(self, name: str) -> None:
        self.config_repository.delete_profile(name)
        self.store.publish(EventType.PROFILE.value, {"name": name, "deleted": True})

    def subscribe(self, *, maxsize: int = 64) -> Subscription:
        return self.store.subscribe(maxsize=maxsize)

    def unsubscribe(self, subscription: Subscription) -> None:
        self.store.unsubscribe(subscription)

    def _section(self, name: str) -> dict[str, Any]:
        with self._config_lock:
            return copy.deepcopy(self._config[name])

    def _clear_config_degraded(self) -> None:
        def updater(current: RuntimeSnapshot) -> RuntimeSnapshot:
            degraded = tuple(item for item in current.health.degraded if item != "config")
            last_error = current.last_error
            if last_error is not None:
                code = last_error.code.value if hasattr(last_error.code, "value") else str(last_error.code)
                if code.startswith("config."):
                    last_error = None
            return replace(current, health=replace(current.health, degraded=degraded), last_error=last_error)

        self.store.mutate(updater)

    def _on_lifecycle(self, notification: LifecycleNotification) -> None:
        error = notification.error.to_snapshot() if notification.error else None

        def updater(current: RuntimeSnapshot) -> RuntimeSnapshot:
            controller_available = notification.state == ConnectionState.CONNECTED
            subsystems = dict(current.health.subsystems)
            subsystems["controller"] = notification.state.value
            degraded = set(current.health.degraded)
            waiting_for_usb = (
                notification.state == ConnectionState.DISCONNECTED
                and notification.error is not None
                and notification.error.code == ErrorCode.CONTROLLER_UNAVAILABLE
            )
            if notification.error and not waiting_for_usb:
                degraded.add("controller")
            elif notification.state in {ConnectionState.CONNECTED, ConnectionState.DISCONNECTED}:
                degraded.discard("controller")
            next_health = replace(
                current.health,
                controller_available=controller_available,
                subsystems=subsystems,
                degraded=tuple(sorted(degraded)),
            )
            last_error = current.last_error
            if notification.state == ConnectionState.CONNECTED:
                last_error = None
            elif error is not None:
                last_error = error
            return replace(current, connection=notification.state, health=next_health, last_error=last_error)

        self.store.mutate(updater)
        self.store.publish(
            EventType.LIFECYCLE.value,
            {"state": notification.state.value, "error": error.to_dict() if error else None},
        )
        LOGGER.info(
            "controller lifecycle changed", extra={"event": "controller.lifecycle", "state": notification.state.value}
        )

    def _on_connected(self, adapter: ControllerAdapter) -> None:
        self.touchpad.set_enabled(self.snapshot().touchpad_enabled)
        self._stop_haptics()
        self._haptics = HapticsService(
            self.controller.set_motors,
            lambda: self._section("rumble"),
            lambda: self.snapshot().rumble_enabled,
            capture_factory=self._capture_factory,
            reload_event=self._reload_audio,
            on_audio=self._on_audio,
            on_error=self._record_error,
        )
        self._haptics.start()
        self.store.mutate(
            lambda current: replace(
                current,
                identity=adapter.identity,
                capabilities=adapter.capabilities,
                health=replace(current.health, subsystems={**current.health.subsystems, "audio": "starting"}),
            )
        )

    def _on_disconnected(self) -> None:
        self._stop_haptics()
        self.touchpad.reset()
        self.store.mutate(
            lambda current: replace(
                current,
                identity=None,
                motors=MotorSnapshot(),
                audio=AudioSnapshot(status="stopped"),
                health=replace(current.health, subsystems={**current.health.subsystems, "audio": "stopped"}),
            )
        )

    def _on_reading(self, reading: Any) -> None:
        # Touch/button input needs the upstream 250 Hz cadence, while battery
        # telemetry should only publish when it actually changes.
        self.touchpad.handle(reading.input)
        if reading.battery != self.snapshot().battery:
            self.store.update(battery=reading.battery)

    def _on_motors(self, left: int, right: int) -> None:
        self.store.update(motors=MotorSnapshot(left, right))

    def _on_audio(self, status: str, device: str | None, error: str | None) -> None:
        def updater(current: RuntimeSnapshot) -> RuntimeSnapshot:
            subsystems = dict(current.health.subsystems)
            subsystems["audio"] = status
            degraded = set(current.health.degraded)
            if status == "error":
                degraded.add("audio")
            elif status in {"listening", "stopped"}:
                degraded.discard("audio")
            return replace(
                current,
                audio=AudioSnapshot(status=status, device=device, error=error),
                health=replace(current.health, subsystems=subsystems, degraded=tuple(sorted(degraded))),
            )

        self.store.mutate(updater)
        self.store.publish(EventType.AUDIO.value, {"status": status, "device": device, "error": error})

    def _on_touch_error(self, error: Exception) -> None:
        wrapped = (
            error
            if isinstance(error, DS5ForgeError)
            else DS5ForgeError(
                ErrorCode.POINTER_OUTPUT_FAILED,
                "Touchpad pointer output failed.",
                detail=str(error),
            )
        )
        self._record_error(wrapped)

    def _record_error(self, error: DS5ForgeError) -> None:
        subsystem = error.code.value.split(".", 1)[0]

        def updater(current: RuntimeSnapshot) -> RuntimeSnapshot:
            degraded = set(current.health.degraded)
            degraded.add(subsystem)
            return replace(
                current,
                last_error=error.to_snapshot(),
                health=replace(current.health, degraded=tuple(sorted(degraded))),
            )

        self.store.mutate(updater)
        self.store.publish(EventType.DIAGNOSTIC.value, {"error": error.to_snapshot().to_dict()})
        LOGGER.warning("runtime error", extra={"event": "runtime.error", "error_code": error.code.value})

    def _stop_haptics(self) -> None:
        haptics, self._haptics = self._haptics, None
        if haptics is not None:
            haptics.stop()
