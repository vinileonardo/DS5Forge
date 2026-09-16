"""The only public runtime surface shared by GUI and local API."""

from __future__ import annotations

import copy
import threading
import time
from dataclasses import replace
from typing import Any

from ..diagnostics.health import health_from_snapshot
from ..diagnostics.logging import get_logger
from ..domain.errors import CapabilityUnavailableError, ConfigValidationError, DS5ForgeError, ErrorCode
from ..domain.events import EventType
from ..domain.exclusive import DuplicateInputDiagnostic, ExclusiveStatus
from ..domain.games import (
    AdaptiveTriggerMode,
    AutomationState,
    CompatibilityMode,
    CompatibilityState,
    ExitPolicy,
    ForegroundApplication,
    GameDefinition,
    ProfileOrigin,
    SyntheticOutputState,
)
from ..domain.models import (
    AdaptiveTriggerEffect,
    AudioSnapshot,
    ConnectionState,
    ControllerCapabilities,
    ControllerInput,
    ControllerTelemetry,
    GestureConfig,
    HapticsTestRun,
    HealthSnapshot,
    LightbarState,
    MotorSnapshot,
    PlayerLedState,
    RuntimeSnapshot,
    StickCalibration,
    TriggerPreviewState,
    TriggerState,
    finite_number,
    normalize_controller_reading,
)
from .adaptive_triggers import AdaptiveTriggerEngine, AdaptiveTriggerStatus, ReactiveTriggerAdapter, TriggerSource
from .calibration import calibrated_sticks
from .config import (
    ConfigRepository,
    default_controller_profile,
    merge_config,
    migrate_controller_profile,
    validate_config,
)
from .controller_lab import HapticsTestBench, TriggerPreviewCoordinator
from .controller_service import ControllerService, LifecycleNotification
from .event_bus import Subscription
from .exclusive_input import ExclusiveCoordinator
from .game_automation import (
    ForegroundWorker,
    conflict_diagnostics,
    evaluate_running_game_rules,
)
from .game_candidates import GameCandidate, merge_candidates
from .games_repository import (
    GameNotFoundError,
    GameRegistryRepository,
    chord_definitions,
    game_definitions,
    mapping_definitions,
)
from .haptics_service import HapticsService
from .input_isolation import InputIsolationCoordinator
from .lightbar import InterruptiblePulseAnimator
from .outputs import OutputManager, RemappingEngine
from .ports import (
    AudioCaptureFactory,
    ControllerAdapter,
    ControllerFactory,
    ForegroundDetector,
    KeyboardOutput,
    MouseOutput,
    ProcessInspector,
    VirtualControllerProvider,
)
from .state_store import StateStore
from .telemetry import TelemetryPublisher
from .touchpad import TouchpadService
from .virtual_controller import virtual_capability

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
        games_repository: GameRegistryRepository | None = None,
        keyboard_output: KeyboardOutput | None = None,
        foreground_detector: ForegroundDetector | None = None,
        process_inspector: ProcessInspector | None = None,
        virtual_provider: VirtualControllerProvider | None = None,
        exclusive_coordinator: ExclusiveCoordinator | None = None,
        input_isolation: InputIsolationCoordinator | None = None,
        game_candidate_provider: Any | None = None,
        foreground_poll_interval: float = 0.75,
    ) -> None:
        self.config_repository = config_repository or ConfigRepository.default()
        self.games_repository = games_repository or GameRegistryRepository.default()
        self._config_lock = threading.RLock()
        self._games_lock = threading.RLock()
        self._automation_lock = threading.RLock()
        self._compatibility_lock = threading.RLock()
        self._config = self.config_repository.load()
        self._games_config = self.games_repository.load()
        self._capture_factory = capture_factory
        self._reload_audio = threading.Event()
        self._haptics: HapticsService | None = None
        self._started = False
        self._stop_lock = threading.Lock()
        self._lab_lock = threading.RLock()
        self._disconnecting = False
        self._last_exclusive_state_publish = 0.0
        self._preview_effect = TriggerState()
        self._last_profile_apply: dict[str, Any] | None = None
        self._foreground_detector = foreground_detector
        self._process_inspector = process_inspector
        self._virtual_provider = virtual_provider
        self._exclusive = exclusive_coordinator or ExclusiveCoordinator()
        self._input_isolation = input_isolation or InputIsolationCoordinator()
        self._exclusive_monitor_stop = threading.Event()
        self._exclusive_monitor: threading.Thread | None = None
        self._last_exclusive_published: ExclusiveStatus = self._exclusive.status()
        self._game_candidate_provider = game_candidate_provider
        self._recent_candidates: list[GameCandidate] = []
        self._recent_candidates_limit = 24
        self._last_running_game_context: tuple[tuple[object, ...], ...] | None = None

        initial_error = self.config_repository.last_error.to_snapshot() if self.config_repository.last_error else None
        if initial_error is None and self.games_repository.last_error is not None:
            initial_error = self.games_repository.last_error.to_snapshot()
        health = HealthSnapshot(
            process_alive=True,
            controller_available=False,
            subsystems={"core": "ready", "controller": "waiting", "audio": "stopped", "touchpad": "ready"},
            degraded=("config",)
            if self.config_repository.last_error
            else ("games",)
            if self.games_repository.last_error
            else (),
        )
        initial = RuntimeSnapshot.initial(
            touchpad_enabled=bool(self._config["trackpad"].get("trackpad_enabled_on_start", True)),
            now=time.time(),
        )
        trackpad = self._config.get("trackpad", {})
        initial = replace(
            initial,
            gesture_config=GestureConfig(
                enabled=bool(trackpad.get("gestures_enabled", True)),
                two_finger_scroll=bool(trackpad.get("two_finger_scroll", True)),
                tap_to_click=bool(trackpad.get("tap_to_click", True)),
                swipe_enabled=bool(trackpad.get("swipe_enabled", True)),
                swipe_threshold=float(trackpad.get("swipe_threshold", 40.0)),
            ),
        )
        persisted_preference = self._games_config.get("compatibility_preference", CompatibilityMode.NATIVE.value)
        initial_mode = (
            CompatibilityMode(persisted_preference)
            if persisted_preference in {CompatibilityMode.NATIVE.value, CompatibilityMode.REMAP.value}
            else CompatibilityMode.NATIVE
        )
        automation_config = self._games_config["automation"]
        initial = replace(
            initial,
            health=health,
            last_error=initial_error,
            automation=AutomationState(
                enabled=automation_config["enabled"],
                exit_policy=ExitPolicy(automation_config["exit_policy"]),
                default_profile=automation_config["default_profile"],
            ),
            compatibility=CompatibilityState(
                mode=initial_mode,
                available=True,
                virtual_capability=virtual_capability(virtual_provider),
                physical_input_visible=True,
                virtual_input_active=False,
                physical_suppression_active=False,
                double_input_risk=initial_mode == CompatibilityMode.REMAP,
                reason=(
                    "Virtual preference is not activated without an approved provider."
                    if persisted_preference == CompatibilityMode.VIRTUAL.value
                    else (
                        "Remap adds keyboard/mouse output while the physical controller remains visible; "
                        "the game or another remapper may also react to the same input."
                        if initial_mode == CompatibilityMode.REMAP
                        else None
                    )
                ),
                changed_at=time.time(),
            ),
            exclusive=self._exclusive.status(),
        )
        self.store = StateStore(initial)

        self._mouse_output = mouse_output
        self._outputs = OutputManager(
            mouse_output,
            keyboard=keyboard_output,
            virtual_provider=virtual_provider,
        )
        self._remapper = RemappingEngine(
            self._outputs,
            mappings=mapping_definitions(self._games_config),
            chords=chord_definitions(self._games_config),
        )
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
        self._lightbar_animator = InterruptiblePulseAnimator(self._apply_lightbar_frame)
        self._adaptive_triggers = AdaptiveTriggerEngine(self.controller, output_supported=False, ttl_seconds=1.0)
        self._reactive_adapter = ReactiveTriggerAdapter()
        self._audio_envelope = 0.0
        self._adaptive_trigger_mode = AdaptiveTriggerMode.NATIVE.value
        self._last_adaptive_status: AdaptiveTriggerStatus = self._adaptive_triggers.status
        self._telemetry = TelemetryPublisher(max_hz=30.0, on_publish=self._on_telemetry)
        self._trigger_preview = TriggerPreviewCoordinator(
            self._apply_trigger_hardware,
            self._reset_trigger_hardware,
            on_state=self._on_trigger_preview,
        )
        self._haptics_bench = HapticsTestBench(
            self.controller.set_motors,
            self.controller.neutralize_motors,
            on_state=self._on_haptics_test,
        )
        self._foreground_worker = (
            ForegroundWorker(
                foreground_detector,
                self._on_foreground_observation,
                on_error=self._record_error,
                interval=foreground_poll_interval,
            )
            if foreground_detector is not None
            else None
        )

    def start(self) -> None:
        with self._stop_lock:
            if self._started:
                return
            self._started = True
            self._disconnecting = False
        LOGGER.info("core starting", extra={"event": "core.start"})
        try:
            recovered_isolation, isolation_status = self._input_isolation.recover_stale()
            if recovered_isolation:
                LOGGER.warning(
                    "recovered stale physical input isolation",
                    extra={"event": "input_isolation.recovered", "status": isolation_status.to_dict()},
                )
        except DS5ForgeError as exc:
            self._record_error(exc)
        recovery = self._exclusive.recover()
        if recovery.performed:
            self._set_exclusive_status(recovery.status, event_type=EventType.EXCLUSIVE_RECOVERED)
        else:
            self._set_exclusive_status(recovery.status)
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
        self._start_exclusive_monitor()
        self.controller.start()
        if self._foreground_worker is not None:
            self._foreground_worker.start()

    def stop(self) -> None:
        with self._stop_lock:
            if not self._started:
                self._disconnecting = True
                if self._foreground_worker is not None:
                    self._foreground_worker.stop()
                self._release_synthetic_outputs("shutdown")
                self._haptics_bench.stop()
                self._best_effort_preview_reset(status="reset")
                self._lightbar_animator.close()
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
                self._close_virtual_provider()
                self._stop_exclusive_monitor()
                self._disable_exclusive(reason="shutdown")
                self._disable_input_isolation(reason="shutdown")
                self._reset_adaptive_triggers(reason="shutdown")
                return
            self._started = False
        LOGGER.info("core stopping", extra={"event": "core.stop"})
        self._disconnecting = True
        if self._foreground_worker is not None:
            self._foreground_worker.stop()
        self._release_synthetic_outputs("shutdown")
        self._haptics_bench.stop()
        self._best_effort_preview_reset(status="reset")
        self._lightbar_animator.close()
        # Stop audio-driven motor writes before neutralizing/stopping the
        # controller. Otherwise the haptics worker can race teardown and write
        # rumble again while ControllerService.stop() is waiting for its thread.
        self._stop_haptics()
        self.controller.stop()
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
        self._close_virtual_provider()
        self._stop_exclusive_monitor()
        self._disable_exclusive(reason="shutdown")
        self._disable_input_isolation(reason="shutdown")
        self._reset_adaptive_triggers(reason="shutdown")

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
        self.store.update(
            config_version=int(result["schema_version"]),
            gesture_config=self._gesture_from_config(result),
        )
        if persist:
            self._clear_config_degraded()
        self.store.publish(EventType.CONFIG.value, {"config": result})
        return result

    def set_rumble_enabled(self, enabled: bool) -> RuntimeSnapshot:
        enabled = bool(enabled)
        snapshot = self.store.update(rumble_enabled=enabled)
        if not enabled:
            self.controller.neutralize_motors()
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
        current = self.snapshot()
        # A disconnected core keeps the historical ``accepted=False`` no-op,
        # but a connected adapter that explicitly reports no rumble surface must
        # never be sent motor output.
        if current.connection == ConnectionState.CONNECTED and not _capability_enabled(current.capabilities, "rumble"):
            capability = current.capabilities.capability("rumble")
            raise CapabilityUnavailableError("rumble", capability.reason)
        return self.controller.pulse(int(left), int(right), int(duration_ms) / 1000)

    def input_telemetry(self) -> ControllerTelemetry:
        return self.snapshot().telemetry

    # ------------------------------------------------------------------
    # P5 Exclusive input and duplicate-input diagnostics

    def exclusive_capability(self) -> dict[str, Any]:
        return self._exclusive.capability().to_dict()

    def exclusive_status(self) -> dict[str, Any]:
        return self._exclusive.status().to_dict()

    def enable_exclusive(self) -> dict[str, Any]:
        with self._compatibility_lock:
            mode = self.snapshot().compatibility.mode
            if mode != CompatibilityMode.NATIVE:
                reason = (
                    "Exclusive input cannot coexist with Remap or Virtual output. "
                    "Return to Native before enabling Exclusive."
                )
                self._set_exclusive_status(replace(self._exclusive.status(), reason=reason, last_error=reason))
                raise DS5ForgeError(
                    ErrorCode.EXCLUSIVE_UNAVAILABLE,
                    reason,
                    fields={"compatibility_mode": mode.value},
                )
            try:
                status = self._exclusive.enable()
            except DS5ForgeError:
                self._set_exclusive_status(self._exclusive.status())
                raise
        self._set_exclusive_status(status)
        return status.to_dict()

    def disable_exclusive(self, *, reason: str = "manual") -> dict[str, Any]:
        return self._disable_exclusive(reason=reason).to_dict()

    def exclusive_heartbeat(self) -> dict[str, Any]:
        status = self._exclusive.heartbeat()
        self._set_exclusive_status(status)
        return status.to_dict()

    def input_isolation_capability(self) -> dict[str, Any]:
        return self._input_isolation.capability().to_dict()

    def input_isolation_status(self) -> dict[str, Any]:
        return self._input_isolation.status().to_dict()

    def enable_input_isolation(self) -> dict[str, Any]:
        with self._compatibility_lock:
            current = self.snapshot().compatibility
            if current.mode != CompatibilityMode.REMAP:
                raise DS5ForgeError(
                    ErrorCode.INPUT_ISOLATION_UNAVAILABLE,
                    "Physical input isolation is only available while Remap mode is active.",
                    fields={"compatibility_mode": current.mode.value},
                )
            if self.snapshot().exclusive.enabled:
                raise DS5ForgeError(
                    ErrorCode.INPUT_ISOLATION_UNAVAILABLE,
                    "Physical input isolation cannot coexist with Exclusive mode.",
                )
            status = self._input_isolation.enable()
            next_state = replace(
                current,
                physical_input_visible=status.physical_input_visible,
                physical_suppression_active=status.active,
                double_input_risk=status.double_input_risk,
                reason=status.reason,
                changed_at=time.time(),
            )
            self.store.update(compatibility=next_state)
            self.store.publish(EventType.COMPATIBILITY_CHANGED.value, {"compatibility": next_state})
        self.duplicate_input_diagnostics()
        return status.to_dict()

    def disable_input_isolation(self, *, reason: str = "manual") -> dict[str, Any]:
        return self._disable_input_isolation(reason=reason).to_dict()

    def _disable_input_isolation(self, *, reason: str) -> Any:
        try:
            status = self._input_isolation.disable()
        except DS5ForgeError as exc:
            self._record_error(exc)
            status = self._input_isolation.status()
        current = self.snapshot().compatibility
        if current.mode == CompatibilityMode.REMAP:
            next_state = replace(
                current,
                physical_input_visible=status.physical_input_visible,
                physical_suppression_active=False,
                double_input_risk=True,
                reason=(
                    f"Physical isolation ended ({reason}); Remap may duplicate physical controller input."
                    if status.last_error is None
                    else f"Physical isolation teardown needs attention: {status.last_error}"
                ),
                changed_at=time.time(),
            )
            self.store.update(compatibility=next_state)
            self.store.publish(EventType.COMPATIBILITY_CHANGED.value, {"compatibility": next_state})
        return status

    def duplicate_input_diagnostics(self) -> dict[str, Any]:
        isolation = self._input_isolation.status()
        compatibility = self.snapshot().compatibility
        if compatibility.mode == CompatibilityMode.REMAP and isolation.active:
            diagnostic = DuplicateInputDiagnostic(
                risk=False,
                physical_visible=isolation.physical_input_visible,
                virtual_active=False,
                suppression_verified=True,
                exclusive_enabled=False,
                severity="success",
                message="Physical DualSense input is isolated for Remap while DS5Forge remains allowlisted.",
                evidence=(
                    f"provider={isolation.capability.provider}",
                    f"device={isolation.device_instance_path or 'unknown'}",
                ),
                checked_at=time.time(),
            )
        else:
            diagnostic = self._exclusive.duplicate_input_diagnostic()
            if compatibility.mode == CompatibilityMode.REMAP:
                evidence = (*diagnostic.evidence, f"input_isolation={isolation.capability.reason or 'available'}")
                diagnostic = replace(
                    diagnostic,
                    risk=True,
                    physical_visible=compatibility.physical_input_visible,
                    virtual_active=False,
                    suppression_verified=False,
                    exclusive_enabled=False,
                    severity="warning",
                    message="Remap is active while the physical DualSense remains visible; duplicate input is possible.",
                    evidence=evidence,
                    checked_at=time.time(),
                )
        self.store.publish(EventType.DUPLICATE_INPUT.value, {"diagnostic": diagnostic})
        return diagnostic.to_dict()

    def _set_exclusive_status(
        self, status: ExclusiveStatus, *, event_type: EventType = EventType.EXCLUSIVE_CHANGED
    ) -> None:
        self._last_exclusive_published = status
        self.store.update(exclusive=status)
        self._last_exclusive_state_publish = time.monotonic()
        self.store.publish(event_type.value, {"exclusive": status})

    def _disable_exclusive(self, *, reason: str) -> ExclusiveStatus:
        status = self._exclusive.disable(reason=reason)
        self._set_exclusive_status(status)
        return status

    def _start_exclusive_monitor(self) -> None:
        if self._exclusive_monitor is not None and self._exclusive_monitor.is_alive():
            return
        self._exclusive_monitor_stop.clear()
        self._exclusive_monitor = threading.Thread(
            target=self._exclusive_monitor_loop,
            name="DS5ForgeExclusiveWatchdog",
            daemon=False,
        )
        self._exclusive_monitor.start()

    def _stop_exclusive_monitor(self, *, join_timeout: float = 2.0) -> None:
        self._exclusive_monitor_stop.set()
        thread = self._exclusive_monitor
        self._exclusive_monitor = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=join_timeout)

    def _exclusive_monitor_loop(self) -> None:
        # Runs independently of the controller read callback so a stalled
        # read/mirror path still expires the Exclusive lease.
        while not self._exclusive_monitor_stop.wait(0.2):
            try:
                status = self._exclusive.tick()
            except Exception:
                LOGGER.exception("exclusive watchdog step failed", extra={"event": "exclusive.watchdog"})
                continue
            if status != self._last_exclusive_published:
                self._set_exclusive_status(status)

    # ------------------------------------------------------------------
    # P5 runtime-reactive adaptive triggers (explicit per-game ownership)

    def adaptive_trigger_status(self) -> dict[str, Any]:
        return self._adaptive_triggers.status.to_dict()

    def _apply_adaptive_trigger_mode(self, game: GameDefinition) -> None:
        mode = game.adaptive_trigger_mode
        value = mode.value if isinstance(mode, AdaptiveTriggerMode) else str(mode)
        previous = self._adaptive_trigger_mode
        self._adaptive_trigger_mode = value
        # Automatic game profile application must never overwrite saved static
        # trigger effects. Ownership is resolved exclusively here:
        #   native   -> leave native game behavior alone, clearing only an
        #               effect DS5Forge previously generated;
        #   off      -> actively neutralize DS5Forge trigger output;
        #   reactive -> start from neutral and let the generated effect take
        #               over from real runtime signal.
        # None of these populate GAME_NATIVE with invented telemetry.
        force = value in {AdaptiveTriggerMode.OFF.value, AdaptiveTriggerMode.REACTIVE.value}
        status = self._adaptive_triggers.reset(reason=f"mode:{value}", force=force)
        self._publish_adaptive_trigger_status(status)
        if value != previous:
            LOGGER.info(
                "adaptive trigger mode changed",
                extra={"event": "adaptive_triggers.mode", "mode": value, "game_id": game.id},
            )

    def _reset_adaptive_triggers(self, *, reason: str) -> None:
        if self._adaptive_trigger_mode == AdaptiveTriggerMode.NATIVE.value:
            # Nothing was generated for native games; avoid needless hardware
            # writes while still clearing any prior reactive session.
            if self._adaptive_triggers.status.source == TriggerSource.OFF:
                return
        self._adaptive_trigger_mode = AdaptiveTriggerMode.NATIVE.value
        self._audio_envelope = 0.0
        status = self._adaptive_triggers.reset(reason=reason)
        self._publish_adaptive_trigger_status(status)

    def _update_reactive_triggers(self, input_state: ControllerInput) -> None:
        if self._adaptive_trigger_mode != AdaptiveTriggerMode.REACTIVE.value:
            return
        if not self._adaptive_triggers.output_supported:
            return
        state = self._reactive_adapter.from_envelope(
            input_state=input_state,
            audio_envelope=self._audio_envelope,
        )
        if state is None:
            status = self._adaptive_triggers.clear_source(TriggerSource.REACTIVE, reason="no_signal")
        else:
            status = self._adaptive_triggers.set_reactive(state, ttl_seconds=0.5)
        self._publish_adaptive_trigger_status(status)

    def _publish_adaptive_trigger_status(self, status: AdaptiveTriggerStatus) -> None:
        previous = self._last_adaptive_status
        if (
            previous.source == status.source
            and previous.generated_effect == status.generated_effect
            and previous.state == status.state
        ):
            self._last_adaptive_status = status
            return
        self._last_adaptive_status = status
        self.store.publish(EventType.ADAPTIVE_TRIGGER_CHANGED.value, {"adaptive_trigger": status.to_dict()})

    def _on_audio_envelope(self, level: float) -> None:
        self._audio_envelope = max(0.0, min(1.0, float(level)))

    def _calibrated_mirror_input(self, input_state: ControllerInput) -> ControllerInput:
        """Apply the configured center/deadzone to Exclusive mirroring only.

        Native telemetry and raw stick values are deliberately unchanged.
        """

        # The configured calibration is always applied for Exclusive mirroring,
        # including the default deadzone. Comparing against a fresh default
        # object would silently skip that default deadzone.
        calibration = self.snapshot().stick_calibration
        sticks = calibrated_sticks(input_state.sticks, calibration, mode="exclusive")
        if sticks == input_state.sticks:
            return input_state
        return replace(input_state, sticks=sticks)

    def lightbar_state(self) -> LightbarState:
        with self._lab_lock:
            try:
                state = self.controller.get_lightbar()
            except DS5ForgeError as exc:
                self._record_error(exc)
                raise
            snapshot = self.store.update(lightbar=state)
            return snapshot.lightbar

    def apply_lightbar(self, state: LightbarState) -> LightbarState:
        _validate_lightbar_state(state)
        with self._lab_lock:
            try:
                self._lightbar_animator.stop()
                pulse_requested = state.enabled and (
                    state.effect in {"pulse", "slow", "fast"} or state.pulse in {"slow", "fast"}
                )
                if pulse_requested:
                    # The software animator is the single authoritative pulse
                    # mechanism; the adapter receives pulse="off" so a hardware
                    # pulse cannot fight the frames.
                    self.controller.set_lightbar(replace(state, pulse="off"))
                    self._lightbar_animator.start(state)
                else:
                    self.controller.set_lightbar(replace(state, pulse="off"))
            except DS5ForgeError as exc:
                if self._best_effort_reset_lightbar():
                    self.store.update(lightbar=LightbarState())
                self._record_error(exc)
                raise
            snapshot = self.store.update(lightbar=state)
            self.store.publish(
                EventType.LAB.value,
                {
                    "kind": "lightbar.applied",
                    "state": state.to_dict() if hasattr(state, "to_dict") else snapshot.to_dict()["lightbar"],
                },
            )
            return snapshot.lightbar

    def reset_lightbar(self) -> LightbarState:
        with self._lab_lock:
            try:
                self._lightbar_animator.stop()
                self.controller.reset_lightbar()
            except DS5ForgeError as exc:
                self._record_error(exc)
                raise
            state = LightbarState()
            snapshot = self.store.update(lightbar=state)
            self.store.publish(EventType.LAB.value, {"kind": "lightbar.reset", "state": snapshot.to_dict()["lightbar"]})
            return snapshot.lightbar

    def _apply_lightbar_frame(self, state: LightbarState) -> None:
        try:
            # Never let an animated frame re-arm a hardware pulse.
            self.controller.set_lightbar(replace(state, pulse="off"))
        except DS5ForgeError as exc:
            self._record_error(exc)
            self.store.update(lightbar=LightbarState())
            self._lightbar_animator.stop()

    def player_led_state(self) -> PlayerLedState:
        with self._lab_lock:
            try:
                state = self.controller.get_player_leds()
            except DS5ForgeError as exc:
                self._record_error(exc)
                raise
            snapshot = self.store.update(player_leds=state)
            return snapshot.player_leds

    def apply_player_leds(self, state: PlayerLedState) -> PlayerLedState:
        if not isinstance(state, PlayerLedState):
            raise ConfigValidationError(fields={"player_leds": "must be a PlayerLedState"})
        with self._lab_lock:
            try:
                self.controller.set_player_leds(state)
            except DS5ForgeError as exc:
                self._record_error(exc)
                raise
            snapshot = self.store.update(player_leds=state)
            self.store.publish(
                EventType.LAB.value,
                {"kind": "player_leds.applied", "player_leds": snapshot.player_leds},
            )
            return snapshot.player_leds

    def reset_player_leds(self) -> PlayerLedState:
        with self._lab_lock:
            try:
                self.controller.reset_player_leds()
            except DS5ForgeError as exc:
                self._record_error(exc)
                raise
            state = PlayerLedState()
            snapshot = self.store.update(player_leds=state)
            self.store.publish(EventType.LAB.value, {"kind": "player_leds.reset", "player_leds": state})
            return snapshot.player_leds

    def trigger_state(self) -> TriggerState:
        return self.snapshot().triggers

    def configure_triggers(self, state: TriggerState) -> TriggerState:
        _validate_trigger_state(state)
        with self._lab_lock:
            try:
                self._trigger_preview.cancel()
            except DS5ForgeError as exc:
                self._record_error(exc)
                raise
            try:
                self.controller.set_triggers(state)
            except DS5ForgeError as exc:
                if self._best_effort_reset_triggers():
                    self.store.update(triggers=TriggerState())
                self._record_error(exc)
                raise
            snapshot = self.store.update(triggers=state)
            self.store.publish(
                EventType.LAB.value, {"kind": "triggers.applied", "state": snapshot.to_dict()["triggers"]}
            )
            return snapshot.triggers

    def preview_triggers(self, state: TriggerState, *, duration_ms: int = 1_000) -> TriggerPreviewState:
        _validate_trigger_state(state)
        with self._lab_lock:
            # Publish the effect being previewed before the coordinator emits its
            # synchronous running state, otherwise the first preview event would
            # report the previously configured effect instead of this one.
            previous_effect = self._preview_effect
            self._preview_effect = state
            try:
                preview = self._trigger_preview.start(state, duration_ms=duration_ms)
            except DS5ForgeError as exc:
                self._preview_effect = previous_effect
                self._record_error(exc)
                raise
            self.store.update(triggers=replace(state, preview=preview))
            return preview

    def cancel_trigger_preview(self) -> TriggerPreviewState | None:
        with self._lab_lock:
            try:
                return self._trigger_preview.cancel()
            except DS5ForgeError as exc:
                self._record_error(exc)
                raise

    def reset_triggers(self) -> TriggerState:
        with self._lab_lock:
            try:
                self._trigger_preview.reset(status="reset")
            except DS5ForgeError as exc:
                self._record_error(exc)
                raise
            try:
                self.controller.reset_triggers()
            except DS5ForgeError as exc:
                self._record_error(exc)
                raise
            snapshot = self.store.update(triggers=TriggerState())
            self.store.publish(EventType.LAB.value, {"kind": "triggers.reset", "state": snapshot.to_dict()["triggers"]})
            return snapshot.triggers

    def haptics_test_state(self) -> HapticsTestRun | None:
        return self.snapshot().haptics_test

    def start_haptics_test(self, *, left: int = 200, right: int = 160, duration_ms: int = 350) -> HapticsTestRun:
        if self.snapshot().connection != ConnectionState.CONNECTED:
            raise DS5ForgeError(
                ErrorCode.CONTROLLER_UNAVAILABLE,
                "A connected USB controller is required for the haptics test.",
            )
        capabilities = self.snapshot().capabilities
        if not _capability_enabled(capabilities, "rumble"):
            capability = capabilities.capability("rumble")
            raise CapabilityUnavailableError("rumble", capability.reason)
        with self._lab_lock:
            self._stop_haptics()
            try:
                return self._haptics_bench.start(left=left, right=right, duration_ms=duration_ms)
            except DS5ForgeError as exc:
                self._record_error(exc)
                self._restart_haptics_if_ready()
                raise

    def cancel_haptics_test(self) -> HapticsTestRun | None:
        return self._haptics_bench.cancel()

    def stick_calibration(self) -> StickCalibration:
        return self.snapshot().stick_calibration

    def update_stick_calibration(self, calibration: StickCalibration) -> StickCalibration:
        _validate_stick_calibration(calibration)
        snapshot = self.store.update(stick_calibration=calibration)
        self.store.publish(
            EventType.LAB.value,
            {"kind": "sticks.calibration_changed", "state": snapshot.to_dict()["stick_calibration"]},
        )
        return snapshot.stick_calibration

    def gesture_config(self) -> GestureConfig:
        return self.snapshot().gesture_config

    def update_gesture_config(self, patch: dict[str, Any]) -> GestureConfig:
        if not isinstance(patch, dict):
            raise ConfigValidationError(fields={"gesture_config": "must be an object"})
        allowed = {"enabled", "two_finger_scroll", "tap_to_click", "swipe_enabled", "swipe_threshold"}
        unknown = sorted(set(patch) - allowed)
        if unknown:
            raise ConfigValidationError(fields={"gesture_config": {"unknown": unknown}})
        current = self.gesture_config()
        merged = {
            "enabled": current.enabled,
            "two_finger_scroll": current.two_finger_scroll,
            "tap_to_click": current.tap_to_click,
            "swipe_enabled": current.swipe_enabled,
            "swipe_threshold": current.swipe_threshold,
            **patch,
        }
        trackpad_patch = {
            "gestures_enabled": merged["enabled"],
            "two_finger_scroll": merged["two_finger_scroll"],
            "tap_to_click": merged["tap_to_click"],
            "swipe_enabled": merged["swipe_enabled"],
            "swipe_threshold": merged["swipe_threshold"],
        }
        if any(not isinstance(value, bool) for key, value in merged.items() if key != "swipe_threshold"):
            raise ConfigValidationError(fields={"gesture_config": "boolean fields must be boolean"})
        if not isinstance(merged["swipe_threshold"], (int, float)) or isinstance(merged["swipe_threshold"], bool):
            raise ConfigValidationError(fields={"swipe_threshold": "must be finite and between 1 and 500"})
        self.update_config({"trackpad": trackpad_patch})
        return self.gesture_config()

    def profiles(self) -> list[dict[str, Any]]:
        return self.config_repository.list_profiles()

    def load_profile(self, name: str) -> dict[str, Any]:
        return self.load_profile_result(name)["config"]

    def load_profile_result(self, name: str) -> dict[str, Any]:
        profile = self.config_repository.load_controller_profile(name)
        result = self.apply_controller_profile(profile, name=name, source=ProfileOrigin.MANUAL)
        self._last_profile_apply = result
        return result

    def controller_profile(self, name: str | None = None) -> dict[str, Any]:
        snapshot = self.snapshot()
        profile = default_controller_profile(name or snapshot.active_profile, rumble=self._section("rumble"))
        profile["lightbar"] = snapshot.to_dict()["lightbar"]
        trigger_dict = snapshot.to_dict()["triggers"]
        profile["triggers"] = {"left": trigger_dict["left"], "right": trigger_dict["right"]}
        profile["sticks"] = snapshot.to_dict()["stick_calibration"]
        profile["touchpad"] = {
            "enabled": snapshot.gesture_config.enabled,
            "two_finger_scroll": snapshot.gesture_config.two_finger_scroll,
            "tap_to_click": snapshot.gesture_config.tap_to_click,
            "swipe_enabled": snapshot.gesture_config.swipe_enabled,
            "swipe_threshold": snapshot.gesture_config.swipe_threshold,
        }
        return migrate_controller_profile(profile, name=profile["name"])

    def apply_controller_profile(
        self,
        profile: dict[str, Any],
        *,
        name: str | None = None,
        source: ProfileOrigin | str = ProfileOrigin.MANUAL,
    ) -> dict[str, Any]:
        with self._automation_lock:
            return self._apply_controller_profile_locked(profile, name=name, source=source)

    def _apply_controller_profile_locked(
        self,
        profile: dict[str, Any],
        *,
        name: str | None = None,
        source: ProfileOrigin | str = ProfileOrigin.MANUAL,
    ) -> dict[str, Any]:
        source = ProfileOrigin(source)
        normalized = migrate_controller_profile(profile, name=name or str(profile.get("name", "Imported")))
        profile_name = name or normalized["name"]
        candidate_trackpad = {
            "gestures_enabled": normalized["touchpad"]["enabled"],
            "two_finger_scroll": normalized["touchpad"]["two_finger_scroll"],
            "tap_to_click": normalized["touchpad"]["tap_to_click"],
            "swipe_enabled": normalized["touchpad"]["swipe_enabled"],
            "swipe_threshold": normalized["touchpad"]["swipe_threshold"],
        }
        candidate = validate_config(
            merge_config(self.config(), {"rumble": normalized["rumble"], "trackpad": candidate_trackpad})
        )
        lightbar = LightbarState(**normalized["lightbar"])
        triggers = TriggerState(
            left=AdaptiveTriggerEffect(**normalized["triggers"]["left"]),
            right=AdaptiveTriggerEffect(**normalized["triggers"]["right"]),
        )
        sticks = StickCalibration(**normalized["sticks"])
        gestures = GestureConfig(
            enabled=normalized["touchpad"]["enabled"],
            two_finger_scroll=normalized["touchpad"]["two_finger_scroll"],
            tap_to_click=normalized["touchpad"]["tap_to_click"],
            swipe_enabled=normalized["touchpad"]["swipe_enabled"],
            swipe_threshold=normalized["touchpad"]["swipe_threshold"],
        )
        # Automatic (game-driven) profile application never writes the saved
        # static adaptive-trigger effect. Trigger ownership for an automatic
        # profile is resolved by `_apply_adaptive_trigger_mode`, so `native`
        # leaves hardware untouched, `off` neutralizes DS5Forge output and
        # `reactive` starts from a neutral generated session. Manual profile
        # application keeps the existing Controller Lab behavior.
        apply_profile_triggers = source == ProfileOrigin.MANUAL
        unsupported: list[str] = []
        with self._lab_lock:
            self._release_synthetic_outputs("profile_change")
            try:
                self._trigger_preview.reset(status="profile_apply")
            except DS5ForgeError as exc:
                self._record_error(exc)
                raise
            current_state = self.snapshot()
            capabilities = current_state.capabilities
            connected = current_state.connection == ConnectionState.CONNECTED
            try:
                if connected and _capability_enabled(capabilities, "lightbar"):
                    self.controller.set_lightbar(lightbar)
                else:
                    unsupported.append("lightbar")
                if apply_profile_triggers:
                    if connected and _capability_enabled(capabilities, "adaptive_triggers"):
                        self.controller.set_triggers(triggers)
                    else:
                        unsupported.append("triggers")
            except DS5ForgeError as exc:
                # A profile is an atomic command from the user's point of
                # view. If a later supported output fails, return every
                # output touched by this attempt to a neutral state before
                # surfacing the typed error, and keep the authoritative
                # snapshot aligned with the hardware that was reset.
                lightbar_reset = self._best_effort_reset_lightbar()
                triggers_reset = self._best_effort_reset_triggers()
                neutral: dict[str, Any] = {}
                if lightbar_reset:
                    neutral["lightbar"] = LightbarState()
                if triggers_reset:
                    neutral["triggers"] = TriggerState()
                if neutral:
                    self.store.update(**neutral)
                self._record_error(exc)
                raise
            self.update_config({"rumble": candidate["rumble"], "trackpad": candidate["trackpad"]}, persist=False)
            snapshot = self.store.update(
                active_profile=profile_name,
                lightbar=lightbar if "lightbar" not in unsupported else self.snapshot().lightbar,
                triggers=triggers if apply_profile_triggers and "triggers" not in unsupported else TriggerState(),
                stick_calibration=sticks,
                gesture_config=gestures,
                automation=replace(
                    self.snapshot().automation,
                    active_profile=profile_name,
                    profile_origin=source,
                ),
            )
            payload = {
                "name": profile_name,
                "source": source.value,
                "config": candidate,
                "unsupported_sections": unsupported,
            }
            self.store.publish(EventType.PROFILE.value, payload)
            if source == ProfileOrigin.MANUAL:
                self._mark_manual_override()
            return {
                "config": candidate,
                "profile": profile_name,
                "unsupported_sections": unsupported,
                "state": snapshot.to_dict(),
            }

    def save_profile(self, name: str, profile: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._config_lock:
            payload = profile if profile is not None else copy.deepcopy(self._config["rumble"])
        saved = self.config_repository.save_profile(name, payload)
        self.store.publish(EventType.PROFILE.value, {"name": name, "source": "user", "saved": True})
        return saved

    def save_controller_profile(
        self,
        name: str,
        profile: dict[str, Any] | None = None,
        *,
        confirm_overwrite: bool = False,
    ) -> dict[str, Any]:
        payload = profile if profile is not None else self.controller_profile(name)
        saved = self.config_repository.save_controller_profile(name, payload, overwrite=confirm_overwrite)
        self.store.publish(
            EventType.PROFILE.value, {"name": name, "source": "user", "saved": True, "schema_version": 2}
        )
        return saved

    def export_profile(self, name: str) -> dict[str, Any]:
        return self.config_repository.load_controller_profile(name)

    def import_profile(
        self,
        content: str,
        *,
        name: str | None = None,
        confirm_overwrite: bool = False,
    ) -> dict[str, Any]:
        imported = self.config_repository.import_controller_profile(
            content,
            name=name,
            overwrite=confirm_overwrite,
        )
        self.store.publish(EventType.PROFILE.value, {"name": imported["name"], "source": "imported", "saved": True})
        return imported

    def delete_profile(self, name: str) -> None:
        self.config_repository.delete_profile(name)
        self.store.publish(EventType.PROFILE.value, {"name": name, "deleted": True})

    # ------------------------------------------------------------------
    # P3 games, automation and compatibility public surface

    def games(self) -> list[dict[str, Any]]:
        with self._games_lock:
            return copy.deepcopy(self._games_config["games"])

    def game_candidates(self) -> list[dict[str, Any]]:
        """Return registered live processes plus bounded recent observations.

        On Windows, the process inspector now supplies real live process
        identities for configured executables, so a background game remains a
        running candidate after Alt+Tab. The recent list is still bounded and
        in-memory only; this endpoint does not perform an unrestricted process
        inventory for the UI.
        """

        foreground = self.snapshot().foreground
        running = [
            GameCandidate(
                executable_name=observation.executable_name or "",
                executable_path=observation.executable_path,
                pid=observation.pid,
                title=observation.title,
                source="running",
                observed_at=observation.observed_at,
            )
            for observation in self._running_game_observations(foreground)
            if observation.executable_name
        ]
        with self._games_lock:
            recent = list(self._recent_candidates)
        provider = self._game_candidate_provider
        if provider is not None:
            try:
                recent = [*provider.recent(), *recent]
            except Exception as exc:
                self._record_error(
                    DS5ForgeError(
                        ErrorCode.FOREGROUND_UNAVAILABLE,
                        "Recent game candidate discovery is unavailable.",
                        detail=str(exc),
                    )
                )
        return [item.to_dict() for item in merge_candidates(running, recent)]

    def _remember_candidate(self, foreground: ForegroundApplication) -> None:
        name = (foreground.executable_name or "").strip()
        if not foreground.available or not name:
            return
        candidate = GameCandidate(
            executable_name=name,
            executable_path=foreground.executable_path,
            pid=foreground.pid,
            title=foreground.title,
            source="recent",
            observed_at=foreground.observed_at or time.time(),
        )
        key = ((candidate.executable_path or "").casefold(), candidate.executable_name.casefold())
        with self._games_lock:
            self._recent_candidates = [
                item
                for item in self._recent_candidates
                if ((item.executable_path or "").casefold(), item.executable_name.casefold()) != key
            ]
            self._recent_candidates.insert(0, candidate)
            del self._recent_candidates[self._recent_candidates_limit :]

    def list_games(self) -> list[dict[str, Any]]:
        return self.games()

    def get_game(self, game_id: str) -> dict[str, Any]:
        target = str(game_id).casefold()
        with self._games_lock:
            for game in self._games_config["games"]:
                if game["id"].casefold() == target:
                    return copy.deepcopy(game)
        raise GameNotFoundError(game_id)

    def add_game(self, game: dict[str, Any]) -> dict[str, Any]:
        with self._automation_lock:
            return self._add_game_locked(game)

    def _add_game_locked(self, game: dict[str, Any]) -> dict[str, Any]:
        candidate = copy.deepcopy(game.to_dict() if hasattr(game, "to_dict") else game)
        with self._games_lock:
            document = copy.deepcopy(self._games_config)
            document["games"].append(candidate)
            normalized = self.games_repository.save(document)
            self._games_config = normalized
            # Validation normalizes surrounding whitespace. Returning the
            # appended normalized record avoids a post-save lookup failure
            # when the request id was valid but not already canonical.
            result = copy.deepcopy(normalized["games"][-1])
        self.store.publish(EventType.AUTOMATION_CHANGED.value, {"kind": "games.changed", "games": self.games()})
        return result

    create_game = add_game

    def update_game(self, game_id: str, game: dict[str, Any]) -> dict[str, Any]:
        with self._automation_lock:
            return self._update_game_locked(game_id, game)

    def _update_game_locked(self, game_id: str, game: dict[str, Any]) -> dict[str, Any]:
        candidate = copy.deepcopy(game.to_dict() if hasattr(game, "to_dict") else game)
        candidate["id"] = str(game_id)
        target = str(game_id).casefold()
        with self._games_lock:
            document = copy.deepcopy(self._games_config)
            index = next(
                (index for index, item in enumerate(document["games"]) if item["id"].casefold() == target), None
            )
            if index is None:
                raise GameNotFoundError(game_id)
            document["games"][index] = candidate
            normalized = self.games_repository.save(document)
            self._games_config = normalized
            result = copy.deepcopy(normalized["games"][index])
        self.store.publish(EventType.AUTOMATION_CHANGED.value, {"kind": "games.changed", "games": self.games()})
        return result

    def delete_game(self, game_id: str) -> None:
        with self._automation_lock:
            self._delete_game_locked(game_id)

    def _delete_game_locked(self, game_id: str) -> None:
        target = str(game_id).casefold()
        with self._games_lock:
            document = copy.deepcopy(self._games_config)
            index = next(
                (index for index, item in enumerate(document["games"]) if item["id"].casefold() == target), None
            )
            if index is None:
                raise GameNotFoundError(game_id)
            document["games"].pop(index)
            normalized = self.games_repository.save(document)
            self._games_config = normalized
        active_game_id = self.snapshot().automation.active_game_id
        if active_game_id is not None and active_game_id.casefold() == target:
            self._deactivate_game(reason="game_removed")
        self.store.publish(EventType.AUTOMATION_CHANGED.value, {"kind": "games.changed", "games": self.games()})

    remove_game = delete_game

    def active_game(self) -> dict[str, Any]:
        automation = self.snapshot().automation
        game = None
        if automation.active_game_id is not None:
            try:
                game = self.get_game(automation.active_game_id)
            except GameNotFoundError:
                game = None
        return {"game": game, "automation": automation.to_dict()}

    def foreground_state(self) -> dict[str, Any]:
        return self.snapshot().foreground.to_dict()

    def test_game_match(self, game_id: str | None = None) -> dict[str, Any]:
        snapshot = self.snapshot()
        foreground = snapshot.foreground
        definitions = list(self._registry_games())
        if game_id is not None:
            definitions = [game for game in definitions if game.id.casefold() == str(game_id).casefold()]
            if not definitions:
                raise GameNotFoundError(game_id)
        running = self._running_game_observations(foreground)
        match, evaluations = evaluate_running_game_rules(
            foreground,
            running,
            definitions,
            active_game_id=snapshot.automation.active_game_id,
        )
        return {
            "matched": match is not None,
            "game_id": match.game_id if match else None,
            "game_name": match.game_name if match else None,
            "reason": match.reason if match else "No registered game rule matched a running process.",
            "foreground": foreground.to_dict(),
            "evaluations": [evaluation.to_dict() for evaluation in evaluations],
        }

    def automation(self) -> dict[str, Any]:
        state = self.snapshot().automation.to_dict()
        state["foreground"] = self.snapshot().foreground.to_dict()
        state["active_game"] = self.active_game()["game"]
        return state

    def update_automation(self, patch: dict[str, Any]) -> dict[str, Any]:
        with self._automation_lock:
            return self._update_automation_locked(patch)

    def _update_automation_locked(self, patch: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(patch, dict):
            raise DS5ForgeError(ErrorCode.GAME_REGISTRY_INVALID, "Automation settings must be an object.")
        allowed = {"enabled", "exit_policy", "default_profile"}
        unknown = sorted(set(patch) - allowed)
        if unknown:
            raise DS5ForgeError(
                ErrorCode.GAME_REGISTRY_INVALID,
                "Automation settings contain unknown fields.",
                fields={"unknown": unknown},
            )
        with self._games_lock:
            document = copy.deepcopy(self._games_config)
            document["automation"].update(copy.deepcopy(patch))
            normalized = self.games_repository.save(document)
            self._games_config = normalized
            automation_config = normalized["automation"]
        current = self.snapshot().automation
        was_enabled = current.enabled
        updated = replace(
            current,
            enabled=automation_config["enabled"],
            exit_policy=ExitPolicy(automation_config["exit_policy"]),
            default_profile=automation_config["default_profile"],
            status="enabled" if automation_config["enabled"] else "disabled",
        )
        self.store.update(automation=updated)
        if not automation_config["enabled"]:
            self._release_synthetic_outputs("automation_disabled")
            if current.active_game_id is not None:
                self._deactivate_game(reason="automation_disabled")
        self.store.publish(EventType.AUTOMATION_CHANGED.value, {"automation": self.automation()})
        if automation_config["enabled"] and not was_enabled:
            # Enabling automation must evaluate the context already observed;
            # waiting for an unrelated foreground transition would make the
            # toggle appear successful while leaving the matching game idle.
            self._evaluate_foreground(self.snapshot().foreground, allow_transition=True)
        return self.automation()

    def compatibility(self) -> dict[str, Any]:
        return self.snapshot().compatibility.to_dict()

    def update_compatibility(self, mode: str) -> dict[str, Any]:
        with self._automation_lock:
            return self._update_compatibility_locked(mode)

    def _update_compatibility_locked(self, mode: str) -> dict[str, Any]:
        try:
            requested = CompatibilityMode(mode)
        except ValueError as exc:
            raise DS5ForgeError(
                ErrorCode.GAME_REGISTRY_INVALID,
                "Compatibility mode is invalid.",
                fields={"mode": "must be native, remap or virtual"},
            ) from exc
        self._set_compatibility_mode(requested, manual=True, persist=True)
        return self.compatibility()

    set_compatibility_mode = update_compatibility

    def mappings(self) -> list[dict[str, Any]]:
        with self._games_lock:
            return copy.deepcopy(self._games_config["mappings"])

    def update_mappings(self, mappings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(mappings, list):
            raise DS5ForgeError(ErrorCode.GAME_REGISTRY_INVALID, "Mappings must be an array.")
        with self._games_lock:
            document = copy.deepcopy(self._games_config)
            document["mappings"] = copy.deepcopy(
                [item.to_dict() if hasattr(item, "to_dict") else item for item in mappings]
            )
            normalized = self.games_repository.save(document)
            self._games_config = normalized
            definitions = mapping_definitions(normalized)
            chords = chord_definitions(normalized)
        self._remapper.configure(definitions, chords)
        self._sync_synthetic_state()
        self.store.publish(
            EventType.AUTOMATION_CHANGED.value, {"kind": "mappings.changed", "mappings": self.mappings()}
        )
        return self.mappings()

    def chords(self) -> list[dict[str, Any]]:
        with self._games_lock:
            return copy.deepcopy(self._games_config["chords"])

    def update_chords(self, chords: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(chords, list):
            raise DS5ForgeError(ErrorCode.GAME_REGISTRY_INVALID, "Chords must be an array.")
        with self._games_lock:
            document = copy.deepcopy(self._games_config)
            document["chords"] = copy.deepcopy(
                [item.to_dict() if hasattr(item, "to_dict") else item for item in chords]
            )
            normalized = self.games_repository.save(document)
            self._games_config = normalized
            definitions = mapping_definitions(normalized)
            chord_values = chord_definitions(normalized)
        self._remapper.configure(definitions, chord_values)
        self._sync_synthetic_state()
        self.store.publish(EventType.AUTOMATION_CHANGED.value, {"kind": "chords.changed", "chords": self.chords()})
        return self.chords()

    def conflict_diagnostics(self) -> list[dict[str, Any]]:
        with self._games_lock:
            names = tuple(self._games_config["conflict_processes"])
        diagnostics = conflict_diagnostics(names, self._process_inspector)
        self.store.update(conflicts=diagnostics)
        return [item.to_dict() for item in diagnostics]

    def subscribe(self, *, maxsize: int = 64) -> Subscription:
        return self.store.subscribe(maxsize=maxsize)

    def unsubscribe(self, subscription: Subscription) -> None:
        self.store.unsubscribe(subscription)

    def release_all_synthetic_outputs(self, reason: str = "manual_release") -> dict[str, Any]:
        return self._release_synthetic_outputs(reason).to_dict()

    def _registry_games(self) -> tuple[GameDefinition, ...]:
        with self._games_lock:
            return game_definitions(self._games_config)

    def _registered_executable_names(self) -> tuple[str, ...]:
        names: list[str] = []
        seen: set[str] = set()
        for game in self._registry_games():
            if not game.enabled:
                continue
            for executable in game.executables:
                key = executable.casefold()
                if key in seen:
                    continue
                seen.add(key)
                names.append(executable)
        return tuple(names)

    def _running_game_observations(
        self,
        foreground: ForegroundApplication,
    ) -> tuple[ForegroundApplication, ...]:
        observations: list[ForegroundApplication] = []
        provider = self._game_candidate_provider
        if provider is not None:
            try:
                for candidate in provider.running():
                    observations.append(
                        ForegroundApplication(
                            available=True,
                            pid=candidate.pid,
                            executable_name=candidate.executable_name,
                            executable_path=candidate.executable_path,
                            title=candidate.title,
                            observed_at=candidate.observed_at or time.time(),
                            process_alive=True,
                        )
                    )
            except Exception as exc:
                LOGGER.warning(
                    "game candidate provider failed during lifecycle polling",
                    extra={"event": "game.candidates_failed", "error": str(exc)},
                )

        inspector_getter = getattr(self._process_inspector, "running_applications", None)
        if callable(inspector_getter):
            try:
                inspected = inspector_getter(self._registered_executable_names())
                if inspected is not None:
                    observations.extend(item for item in inspected if isinstance(item, ForegroundApplication))
            except Exception as exc:
                LOGGER.warning(
                    "running game process inspection failed",
                    extra={"event": "game.running_processes_failed", "error": str(exc)},
                )

        if foreground.available and foreground.process_alive and foreground.executable_name:
            observations.insert(0, foreground)

        deduplicated: list[ForegroundApplication] = []
        seen: set[tuple[object, ...]] = set()
        for observation in observations:
            key = (
                observation.pid,
                (observation.executable_name or "").casefold(),
                (observation.executable_path or "").casefold(),
            )
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(observation)
        return tuple(deduplicated)

    @staticmethod
    def _running_context_key(
        running: tuple[ForegroundApplication, ...],
    ) -> tuple[tuple[object, ...], ...]:
        return tuple(
            sorted(
                (
                    item.pid or 0,
                    (item.executable_name or "").casefold(),
                    (item.executable_path or "").casefold(),
                )
                for item in running
            )
        )

    def _on_foreground_observation(self, foreground: ForegroundApplication, changed: bool) -> None:
        previous = self.snapshot().foreground
        self.store.update(foreground=foreground)
        self._remember_candidate(foreground)
        if changed:
            self.store.publish(
                EventType.GAME_FOREGROUND_CHANGED.value,
                {"foreground": foreground, "changed": changed, "previous": previous},
            )
        running = self._running_game_observations(foreground)
        running_context = self._running_context_key(running)
        running_changed = running_context != self._last_running_game_context
        self._last_running_game_context = running_context
        self._evaluate_foreground(
            foreground,
            running=running,
            allow_transition=changed or running_changed,
        )

    def _evaluate_foreground(
        self,
        foreground: ForegroundApplication,
        *,
        running: tuple[ForegroundApplication, ...] | None = None,
        allow_transition: bool,
    ) -> None:
        live = running if running is not None else self._running_game_observations(foreground)
        with self._automation_lock:
            self._evaluate_foreground_locked(foreground, running=live, allow_transition=allow_transition)

    def _evaluate_foreground_locked(
        self,
        foreground: ForegroundApplication,
        *,
        running: tuple[ForegroundApplication, ...],
        allow_transition: bool,
    ) -> None:
        current_automation = self.snapshot().automation
        match, evaluations = evaluate_running_game_rules(
            foreground,
            running,
            self._registry_games(),
            active_game_id=current_automation.active_game_id,
        )
        evaluated = replace(current_automation, last_match=match, rule_evaluations=evaluations)
        self.store.update(automation=evaluated)
        self.store.publish(
            EventType.GAME_DETECTED.value,
            {
                "match": match,
                "evaluations": evaluations,
                "foreground": foreground,
            },
        )
        if not allow_transition or not evaluated.enabled:
            return
        if match is not None:
            match_game_id = match.game_id
            same_active_game = bool(
                evaluated.active_game_id
                and match_game_id is not None
                and evaluated.active_game_id.casefold() == match_game_id.casefold()
            )
            if same_active_game:
                previous_match = current_automation.last_match
                previous_pid = previous_match.foreground.pid if previous_match is not None else None
                selected_pid = match.foreground.pid
                # Alt+Tab keeps the same live process active. A different PID
                # for the same rule is a genuine process restart and must
                # re-run automation, including superseding a manual override.
                if previous_pid is None or selected_pid is None or previous_pid == selected_pid:
                    return
                self._deactivate_game(reason="game_process_change", apply_exit=False, clear_previous=False)
                self._activate_game(match_game_id)
                return
            if evaluated.active_game_id is not None:
                self._deactivate_game(reason="game_change", apply_exit=False, clear_previous=False)
            self._activate_game(match_game_id)
        elif evaluated.active_game_id is not None:
            self._deactivate_game(reason="game_process_exit")

    def _activate_game(self, game_id: str | None) -> None:
        if game_id is None:
            return
        game = next((item for item in self._registry_games() if item.id.casefold() == game_id.casefold()), None)
        if game is None:
            self._record_error(GameNotFoundError(game_id))
            return
        current = self.snapshot()
        automation = current.automation
        previous_profile = automation.previous_profile or current.active_profile
        previous_mode = automation.previous_compatibility_mode or current.compatibility.mode
        rollback_mode = current.compatibility.mode
        mode_changed = rollback_mode != game.compatibility_mode
        try:
            # Read and validate the profile before changing compatibility or
            # releasing outputs, so a bad registry reference is atomic.
            profile = self.config_repository.load_controller_profile(game.profile)
            self._ensure_compatibility_available(game.compatibility_mode)
            if mode_changed:
                self._set_compatibility_mode(game.compatibility_mode, manual=False, persist=False)
            self.apply_controller_profile(profile, name=game.profile, source=ProfileOrigin.AUTOMATIC)
            self._apply_adaptive_trigger_mode(game)
            self._remapper.set_game_context(game.id)
        except DS5ForgeError as exc:
            self._reset_adaptive_triggers(reason="activation_failed")
            if mode_changed and self.snapshot().compatibility.mode != rollback_mode:
                try:
                    self._set_compatibility_mode(rollback_mode, manual=False, persist=False)
                except DS5ForgeError as rollback_error:
                    self._record_error(rollback_error)
            self._record_error(exc)
            recovery_error = self._recover_failed_game_transition()
            diagnostic = exc.message
            if recovery_error is not None:
                diagnostic = f"{diagnostic} Recovery failed: {recovery_error.message}"
            self.store.update(
                automation=replace(
                    self.snapshot().automation,
                    status="error",
                    diagnostic=diagnostic,
                )
            )
            self.store.publish(
                EventType.GAME_RULE_APPLIED.value,
                {"game_id": game.id, "matched": True, "applied": False, "error": exc.to_snapshot()},
            )
            return
        updated = replace(
            self.snapshot().automation,
            active_game_id=game.id,
            active_game_name=game.name,
            active_profile=game.profile,
            profile_origin=ProfileOrigin.AUTOMATIC,
            manual_override=False,
            previous_profile=previous_profile,
            previous_compatibility_mode=previous_mode,
            transition=self.snapshot().automation.transition + 1,
            last_transition_at=time.time(),
            status="active",
            diagnostic=None,
        )
        self.store.update(automation=updated)
        self.store.publish(
            EventType.GAME_ACTIVATED.value,
            {
                "game": game.to_dict(),
                "profile": game.profile,
                "profile_origin": ProfileOrigin.AUTOMATIC.value,
                "compatibility": self.compatibility(),
            },
        )
        self.store.publish(
            EventType.GAME_RULE_APPLIED.value,
            {"game_id": game.id, "matched": True, "applied": True, "profile": game.profile},
        )
        self._publish_conflict_events()

    def _recover_failed_game_transition(self) -> DS5ForgeError | None:
        """Restore the configured exit state after an A -> B activation failure.

        A game-to-game transition intentionally skips the first game's exit
        policy to avoid a visible profile/mode bounce when B activates
        successfully. If B fails, however, leaving A's settings applied while
        no game is authoritative would strand game-specific state on the
        desktop. Recover using the preserved baseline and then clear it.
        """

        automation = self.snapshot().automation
        if automation.active_game_id is not None or automation.previous_profile is None:
            return None
        policy = automation.exit_policy
        recovery_error: DS5ForgeError | None = None
        try:
            if policy == ExitPolicy.RESTORE_PREVIOUS:
                profile_name = automation.previous_profile
                profile = self.config_repository.load_controller_profile(profile_name)
                if automation.previous_compatibility_mode is not None:
                    self._ensure_compatibility_available(automation.previous_compatibility_mode)
                    if self.snapshot().compatibility.mode != automation.previous_compatibility_mode:
                        self._set_compatibility_mode(
                            automation.previous_compatibility_mode,
                            manual=False,
                            persist=False,
                        )
                self.apply_controller_profile(profile, name=profile_name, source=ProfileOrigin.AUTOMATIC)
            elif policy == ExitPolicy.APPLY_DEFAULT:
                profile_name = automation.default_profile
                profile = self.config_repository.load_controller_profile(profile_name)
                self._set_compatibility_mode(CompatibilityMode.NATIVE, manual=False, persist=False)
                self.apply_controller_profile(profile, name=profile_name, source=ProfileOrigin.AUTOMATIC)
        except DS5ForgeError as exc:
            recovery_error = exc
            self._record_error(exc)
        finally:
            current = self.snapshot().automation
            self.store.update(
                automation=replace(
                    current,
                    active_profile=self.snapshot().active_profile,
                    previous_profile=None,
                    previous_compatibility_mode=None,
                )
            )
        return recovery_error

    def _deactivate_game(
        self,
        *,
        reason: str,
        apply_exit: bool = True,
        clear_previous: bool = True,
    ) -> None:
        current = self.snapshot()
        automation = current.automation
        game_id = automation.active_game_id
        if game_id is None:
            self._reset_adaptive_triggers(reason=reason)
            self._release_synthetic_outputs(reason)
            return
        self._reset_adaptive_triggers(reason=reason)
        self._release_synthetic_outputs(reason)
        self._remapper.set_game_context(None, release=False)
        policy = ExitPolicy.KEEP_CURRENT if automation.manual_override else automation.exit_policy
        applied_profile: str | None = None
        action = policy.value
        if apply_exit:
            try:
                if policy == ExitPolicy.RESTORE_PREVIOUS and automation.previous_profile:
                    profile_name = automation.previous_profile
                    profile = self.config_repository.load_controller_profile(profile_name)
                    if automation.previous_compatibility_mode is not None:
                        self._ensure_compatibility_available(automation.previous_compatibility_mode)
                        if self.snapshot().compatibility.mode != automation.previous_compatibility_mode:
                            self._set_compatibility_mode(
                                automation.previous_compatibility_mode,
                                manual=False,
                                persist=False,
                            )
                    self.apply_controller_profile(profile, name=profile_name, source=ProfileOrigin.AUTOMATIC)
                    applied_profile = profile_name
                elif policy == ExitPolicy.APPLY_DEFAULT:
                    profile_name = automation.default_profile
                    profile = self.config_repository.load_controller_profile(profile_name)
                    self._set_compatibility_mode(CompatibilityMode.NATIVE, manual=False, persist=False)
                    self.apply_controller_profile(profile, name=profile_name, source=ProfileOrigin.AUTOMATIC)
                    applied_profile = profile_name
            except DS5ForgeError as exc:
                self._record_error(exc)
                action = f"{policy.value}:failed"
        updated = replace(
            self.snapshot().automation,
            active_game_id=None,
            active_game_name=None,
            active_profile=applied_profile or self.snapshot().active_profile,
            profile_origin=ProfileOrigin.MANUAL if automation.manual_override else ProfileOrigin.AUTOMATIC,
            manual_override=False,
            previous_profile=None if clear_previous else automation.previous_profile,
            previous_compatibility_mode=None if clear_previous else automation.previous_compatibility_mode,
            transition=self.snapshot().automation.transition + 1,
            last_transition_at=time.time(),
            status="enabled" if automation.enabled else "disabled",
            diagnostic=None,
        )
        self.store.update(automation=updated)
        self.store.publish(
            EventType.GAME_DEACTIVATED.value,
            {
                "game_id": game_id,
                "reason": reason,
                "exit_policy": policy.value,
                "applied_profile": applied_profile,
                "action": action,
            },
        )

    def _mark_manual_override(self) -> None:
        current = self.snapshot()
        if current.automation.active_game_id is None:
            return
        updated = replace(
            current.automation,
            active_profile=current.active_profile,
            profile_origin=ProfileOrigin.MANUAL,
            manual_override=True,
            status="manual_override",
        )
        self.store.update(automation=updated)
        self.store.publish(
            EventType.AUTOMATION_CHANGED.value,
            {"automation": self.automation(), "reason": "manual_override"},
        )

    def _ensure_compatibility_available(self, mode: CompatibilityMode) -> None:
        if mode != CompatibilityMode.VIRTUAL:
            return
        capability = virtual_capability(self._virtual_provider)
        if not capability.operational:
            raise DS5ForgeError(
                ErrorCode.COMPATIBILITY_UNAVAILABLE,
                "Virtual / XInput mode is unavailable in this P3 build.",
                detail=capability.reason,
                fields={"mode": mode.value, "capability": capability.to_dict()},
            )

    def _set_compatibility_mode(self, mode: CompatibilityMode, *, manual: bool, persist: bool) -> None:
        with self._compatibility_lock:
            self._set_compatibility_mode_locked(mode, manual=manual, persist=persist)

    def _set_compatibility_mode_locked(self, mode: CompatibilityMode, *, manual: bool, persist: bool) -> None:
        self._ensure_compatibility_available(mode)
        if mode != CompatibilityMode.NATIVE and self.snapshot().exclusive.enabled:
            # Exclusive owns physical suppression; never let Remap/Virtual run
            # at the same time. Disabling first keeps the teardown deterministic.
            self._disable_exclusive(reason="compatibility_mode_change")
        current = self.snapshot().compatibility
        if mode != CompatibilityMode.REMAP and self._input_isolation.status().active:
            self._disable_input_isolation(reason="compatibility_mode_change")
            current = self.snapshot().compatibility
        if current.mode == mode:
            if manual:
                self._mark_manual_override()
            return
        self._release_synthetic_outputs("mode_change")
        if mode == CompatibilityMode.VIRTUAL:
            provider = self._virtual_provider
            if provider is None:
                # _ensure_compatibility_available already raises; this keeps
                # the type/runtime boundary explicit for future providers.
                raise DS5ForgeError(
                    ErrorCode.VIRTUAL_PROVIDER_UNAVAILABLE, "No virtual-controller provider is configured."
                )
            try:
                provider.start()
            except Exception as exc:
                try:
                    provider.close()
                except Exception as close_error:
                    LOGGER.warning(
                        "virtual provider cleanup after start failure failed",
                        extra={"event": "virtual.start_cleanup", "error": str(close_error)},
                    )
                raise DS5ForgeError(
                    ErrorCode.COMPATIBILITY_UNAVAILABLE,
                    "Virtual / XInput provider could not start.",
                    detail=str(exc),
                ) from exc
            self._outputs.set_virtual_active(True)
        else:
            self._outputs.set_virtual_active(False)
        try:
            if persist:
                with self._games_lock:
                    document = copy.deepcopy(self._games_config)
                    document["compatibility_preference"] = mode.value
                    self._games_config = self.games_repository.save(document)
        except DS5ForgeError:
            if mode == CompatibilityMode.VIRTUAL and current.mode != CompatibilityMode.VIRTUAL:
                self._close_virtual_provider()
            elif current.mode == CompatibilityMode.VIRTUAL:
                self._outputs.set_virtual_active(True)
            else:
                self._outputs.set_virtual_active(False)
            raise
        if current.mode == CompatibilityMode.VIRTUAL and mode != CompatibilityMode.VIRTUAL:
            self._close_virtual_provider()
        capability = virtual_capability(self._virtual_provider)
        next_state = CompatibilityState(
            mode=mode,
            available=True,
            virtual_capability=capability,
            physical_input_visible=mode != CompatibilityMode.VIRTUAL,
            virtual_input_active=mode == CompatibilityMode.VIRTUAL,
            physical_suppression_active=mode == CompatibilityMode.VIRTUAL,
            double_input_risk=mode == CompatibilityMode.REMAP,
            reason=(
                "Physical input suppression is provided by the injected provider."
                if mode == CompatibilityMode.VIRTUAL
                else (
                    "Remap adds keyboard/mouse output while the physical controller remains visible; "
                    "the game or another remapper may also react to the same input."
                    if mode == CompatibilityMode.REMAP
                    else None
                )
            ),
            changed_at=time.time(),
        )
        self.store.update(compatibility=next_state)
        self.store.publish(EventType.COMPATIBILITY_CHANGED.value, {"compatibility": next_state})
        if manual:
            self._mark_manual_override()

    def _sync_synthetic_state(self) -> None:
        held = self._outputs.held
        current = self.snapshot().synthetic_outputs
        if current.held != held:
            self.store.update(synthetic_outputs=replace(current, held=held, release_status="held" if held else "idle"))

    def _release_synthetic_outputs(self, reason: str):
        report = self._remapper.release_all(reason=reason)
        self.store.update(
            synthetic_outputs=SyntheticOutputState(
                held=(),
                last_release=report,
                release_status="failed" if report.failures else "released",
            )
        )
        self.store.publish(EventType.SYNTHETIC_RELEASE.value, {"report": report})
        if report.failures:
            self._record_error(
                DS5ForgeError(
                    ErrorCode.SYNTHETIC_OUTPUT_FAILED,
                    "One or more synthetic outputs could not be released.",
                    detail="; ".join(report.failures),
                    fields={"reason": reason, "failures": list(report.failures)},
                )
            )
        return report

    def _publish_conflict_events(self) -> None:
        for diagnostic in self.conflict_diagnostics():
            if diagnostic.get("running"):
                self.store.publish(EventType.GAME_CONFLICT_DETECTED.value, {"conflict": diagnostic})

    def _close_virtual_provider(self) -> None:
        self._outputs.set_virtual_active(False)
        provider = self._virtual_provider
        if provider is None:
            return
        try:
            provider.close()
        except Exception as exc:
            LOGGER.warning("virtual provider close failed", extra={"event": "virtual.close", "error": str(exc)})

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

        if notification.state in {
            ConnectionState.DISCONNECTED,
            ConnectionState.RECONNECTING,
            ConnectionState.ERROR,
            ConnectionState.STOPPING,
        }:
            self._release_synthetic_outputs(f"controller_{notification.state.value}")

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
            capabilities = (
                current.capabilities
                if notification.state == ConnectionState.CONNECTED
                else ControllerCapabilities.unavailable(
                    "No connected USB controller is available; reconnect to detect capabilities."
                )
            )
            return replace(
                current,
                connection=notification.state,
                capabilities=capabilities,
                health=next_health,
                last_error=last_error,
            )

        self.store.mutate(updater)
        self.store.publish(
            EventType.LIFECYCLE.value,
            {"state": notification.state.value, "error": error.to_dict() if error else None},
        )
        LOGGER.info(
            "controller lifecycle changed", extra={"event": "controller.lifecycle", "state": notification.state.value}
        )

    def _on_connected(self, adapter: ControllerAdapter) -> None:
        self._disconnecting = False
        self._lightbar_animator.stop()
        if self.snapshot().exclusive.enabled:
            self._disable_exclusive(reason="controller_reconnected")
        else:
            self._set_exclusive_status(self._exclusive.status())
        self._release_synthetic_outputs("controller_connected")
        # Reconnects begin from a known neutral trigger/output state. The
        # adapter is still owned by ControllerService at this point.
        try:
            self._trigger_preview.reset(status="reconnect")
        except DS5ForgeError as exc:
            self._record_error(exc)
        self._best_effort_reset_triggers()
        capabilities = self._active_capabilities()
        self._adaptive_triggers.set_output_supported(bool(getattr(capabilities, "adaptive_triggers", False)))
        self._reset_adaptive_triggers(reason="controller_connected")
        self._telemetry.reset()
        self.touchpad.set_enabled(self.snapshot().touchpad_enabled)
        self._stop_haptics()
        self._haptics = HapticsService(
            self.controller.set_motors,
            lambda: self._section("rumble"),
            lambda: self.snapshot().rumble_enabled,
            capture_factory=self._capture_factory,
            reload_event=self._reload_audio,
            on_audio=self._on_audio,
            on_envelope=self._on_audio_envelope,
            on_error=self._record_error,
        )
        self._haptics.start()
        lightbar = self.snapshot().lightbar
        getter = getattr(adapter, "get_lightbar", None)
        if callable(getter):
            try:
                candidate = getter()
                if isinstance(candidate, LightbarState):
                    lightbar = candidate
            except Exception as exc:
                LOGGER.warning(
                    "lightbar state could not be read", extra={"event": "controller.lightbar_read", "error": str(exc)}
                )
        player_leds = self.snapshot().player_leds
        player_getter = getattr(adapter, "get_player_leds", None)
        if callable(player_getter):
            try:
                candidate = player_getter()
                if isinstance(candidate, PlayerLedState):
                    player_leds = candidate
            except Exception as exc:
                LOGGER.warning(
                    "player LED state could not be read",
                    extra={"event": "controller.player_led_read", "error": str(exc)},
                )
        self.store.mutate(
            lambda current: replace(
                current,
                identity=adapter.identity,
                capabilities=adapter.capabilities,
                motors=MotorSnapshot(),
                input=ControllerInput(),
                telemetry=ControllerTelemetry(),
                lightbar=lightbar,
                player_leds=player_leds,
                triggers=TriggerState(),
                haptics_test=None,
                health=replace(current.health, subsystems={**current.health.subsystems, "audio": "starting"}),
            )
        )

    def _on_disconnected(self) -> None:
        self._disconnecting = True
        self._lightbar_animator.stop()
        self._disable_exclusive(reason="controller_disconnected")
        self._reset_adaptive_triggers(reason="controller_disconnected")
        self._adaptive_triggers.set_output_supported(False)
        self._release_synthetic_outputs("controller_disconnected")
        try:
            self._trigger_preview.reset(status="disconnect")
        except DS5ForgeError as exc:
            self._record_error(exc)
        self._best_effort_reset_triggers()
        self._best_effort_reset_player_leds()
        self._telemetry.reset()
        self._haptics_bench.stop()
        self._stop_haptics()
        self.touchpad.reset()
        self.store.mutate(
            lambda current: replace(
                current,
                identity=None,
                motors=MotorSnapshot(),
                input=ControllerInput(),
                telemetry=ControllerTelemetry(),
                triggers=TriggerState(),
                player_leds=PlayerLedState(),
                haptics_test=None,
                audio=AudioSnapshot(status="stopped"),
                health=replace(current.health, subsystems={**current.health.subsystems, "audio": "stopped"}),
            )
        )

    def _on_reading(self, reading: Any) -> None:
        # Touch/button input needs the upstream 250 Hz cadence, while battery
        # telemetry should only publish when it actually changes.
        reading = normalize_controller_reading(reading)
        if self.snapshot().exclusive.enabled:
            try:
                mirror_input = self._calibrated_mirror_input(reading.input)
                if mirror_input is reading.input:
                    mirrored = reading
                else:
                    mirrored = replace(reading, input=mirror_input)
                status = self._exclusive.mirror_reading(mirrored)
                now = time.monotonic()
                if now - self._last_exclusive_state_publish >= 1.0 / 30.0:
                    self._set_exclusive_status(status)
            except DS5ForgeError as exc:
                self._record_error(exc)
        self._update_reactive_triggers(reading.input)
        self.touchpad.handle(reading.input)
        with self._compatibility_lock:
            if self.snapshot().compatibility.mode == CompatibilityMode.REMAP:
                try:
                    self._remapper.process(
                        reading.input.buttons,
                        now=reading.timestamp if reading.timestamp > 0 else time.monotonic(),
                    )
                except DS5ForgeError as exc:
                    self._record_error(exc)
                self._sync_synthetic_state()
        # A completely empty compatibility reading is already represented by
        # the initial snapshot. Avoid turning legacy battery-only callbacks
        # into a state event while still publishing the first meaningful lab
        # sample immediately.
        if reading.input != ControllerInput() or self._telemetry.latest is not None:
            self._telemetry.offer(reading.input, timestamp=reading.timestamp if reading.timestamp > 0 else None)
        if reading.battery != self.snapshot().battery:
            self.store.update(battery=reading.battery)

    def _on_telemetry(self, telemetry: ControllerTelemetry) -> None:
        self.store.update(input=telemetry.input, telemetry=telemetry)
        self.store.publish(
            EventType.CONTROLLER_INPUT.value,
            {"input": telemetry.input, "telemetry": telemetry},
        )

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

    def _apply_trigger_hardware(self, state: TriggerState) -> None:
        self.controller.set_triggers(state)

    def _reset_trigger_hardware(self) -> None:
        if not _capability_enabled(self._active_capabilities(), "adaptive_triggers"):
            return
        self.controller.reset_triggers()

    def _best_effort_reset_triggers(self) -> bool:
        if not _capability_enabled(self._active_capabilities(), "adaptive_triggers"):
            return False
        try:
            self._reset_trigger_hardware()
        except DS5ForgeError as exc:
            LOGGER.error(
                "best-effort trigger reset failed",
                extra={"event": "controller.trigger_reset", "error_code": exc.code.value},
            )
            return False
        return True

    def _best_effort_preview_reset(self, *, status: str) -> None:
        try:
            self._trigger_preview.reset(status=status)
        except DS5ForgeError as exc:
            self._record_error(exc)

    def _best_effort_reset_lightbar(self) -> bool:
        if not _capability_enabled(self._active_capabilities(), "lightbar"):
            return False
        try:
            self.controller.reset_lightbar()
        except DS5ForgeError as exc:
            LOGGER.error(
                "best-effort lightbar reset failed",
                extra={"event": "controller.lightbar_reset", "error_code": exc.code.value},
            )
            return False
        return True

    def _best_effort_reset_player_leds(self) -> bool:
        if not _capability_enabled(self._active_capabilities(), "lightbar"):
            return False
        try:
            self.controller.reset_player_leds()
        except DS5ForgeError as exc:
            LOGGER.error(
                "best-effort Player LED reset failed",
                extra={"event": "controller.player_led_reset", "error_code": exc.code.value},
            )
            return False
        return True

    def _active_capabilities(self) -> Any:
        adapter = self.controller.adapter
        return getattr(adapter, "capabilities", self.snapshot().capabilities)

    def _on_trigger_preview(self, preview: TriggerPreviewState) -> None:
        with self._lab_lock:
            if preview.status == "running":
                triggers = replace(self._preview_effect, preview=preview)
            else:
                triggers = TriggerState(preview=preview)
            snapshot = self.store.update(triggers=triggers)
            self.store.publish(
                EventType.LAB.value,
                {"kind": "triggers.preview", "preview": preview, "state": snapshot.to_dict()["triggers"]},
            )

    def _on_haptics_test(self, run: HapticsTestRun) -> None:
        with self._lab_lock:
            self.store.update(haptics_test=run)
            self.store.publish(EventType.LAB.value, {"kind": "haptics.test", "run": run})
            if run.status != "running":
                self._restart_haptics_if_ready()

    def _restart_haptics_if_ready(self) -> None:
        if self._haptics is not None or not self._started or self._disconnecting:
            return
        # Audio-driven rumble must stay paused for the whole duration of a bench
        # run. A duplicate start request is rejected as busy but must not resume
        # audio output while the existing run is still active.
        active_run = self._haptics_bench.run
        if active_run is not None and active_run.status == "running":
            return
        if self.snapshot().connection != ConnectionState.CONNECTED:
            return
        self._haptics = HapticsService(
            self.controller.set_motors,
            lambda: self._section("rumble"),
            lambda: self.snapshot().rumble_enabled,
            capture_factory=self._capture_factory,
            reload_event=self._reload_audio,
            on_audio=self._on_audio,
            on_envelope=self._on_audio_envelope,
            on_error=self._record_error,
        )
        self._haptics.start()

    @staticmethod
    def _gesture_from_config(config: dict[str, Any]) -> GestureConfig:
        trackpad = config.get("trackpad", {})
        return GestureConfig(
            enabled=bool(trackpad.get("gestures_enabled", True)),
            two_finger_scroll=bool(trackpad.get("two_finger_scroll", True)),
            tap_to_click=bool(trackpad.get("tap_to_click", True)),
            swipe_enabled=bool(trackpad.get("swipe_enabled", True)),
            swipe_threshold=float(trackpad.get("swipe_threshold", 40.0)),
        )


def _validate_lightbar_state(state: LightbarState) -> None:
    if not isinstance(state, LightbarState):
        raise ConfigValidationError(fields={"lightbar": "must be a LightbarState"})
    if any(
        not isinstance(getattr(state, key), int) or isinstance(getattr(state, key), bool) for key in ("r", "g", "b")
    ):
        raise ConfigValidationError(fields={"lightbar": "color channels must be integers"})
    if not all(0 <= getattr(state, key) <= 255 for key in ("r", "g", "b")):
        raise ConfigValidationError(fields={"lightbar": "color channels must be between 0 and 255"})
    if (
        not isinstance(state.enabled, bool)
        or not isinstance(state.brightness, int)
        or isinstance(state.brightness, bool)
    ):
        raise ConfigValidationError(fields={"lightbar": "enabled and brightness have invalid types"})
    if (
        not 0 <= state.brightness <= 2
        or state.pulse not in {"off", "slow", "fast"}
        or state.effect not in {"steady", "pulse", "slow", "fast"}
        or not finite_number(state.intensity)
        or not 0 <= state.intensity <= 1
    ):
        raise ConfigValidationError(fields={"lightbar": "brightness or pulse is invalid"})


def _capability_enabled(capabilities: Any, name: str) -> bool:
    availability = getattr(capabilities, "availability", {}).get(name)
    if availability is not None:
        return bool(getattr(availability, "enabled", False))
    return bool(getattr(capabilities, name, False))


def _validate_trigger_state(state: TriggerState) -> None:
    if not isinstance(state, TriggerState):
        raise ConfigValidationError(fields={"triggers": "must be a TriggerState"})
    for side, effect in (("left", state.left), ("right", state.right)):
        if not isinstance(effect.mode, str) or effect.mode not in {"off", "resistance", "pulse", "rigid"}:
            raise ConfigValidationError(fields={f"triggers.{side}.mode": "unsupported trigger mode"})
        for key in ("start_position", "end_position", "force", "frequency", "amplitude"):
            value = getattr(effect, key)
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 255:
                raise ConfigValidationError(fields={f"triggers.{side}.{key}": "must be an integer between 0 and 255"})
        if effect.start_position > effect.end_position:
            raise ConfigValidationError(fields={f"triggers.{side}.start_position": "must not exceed end_position"})


def _validate_stick_calibration(calibration: StickCalibration) -> None:
    if not isinstance(calibration, StickCalibration):
        raise ConfigValidationError(fields={"sticks": "must be a StickCalibration"})
    for key in (
        "left_deadzone",
        "right_deadzone",
        "left_center_x",
        "left_center_y",
        "right_center_x",
        "right_center_y",
    ):
        value = getattr(calibration, key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ConfigValidationError(fields={f"sticks.{key}": "must be a finite number"})
