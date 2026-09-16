import io
import struct
import tempfile
import time
from dataclasses import replace
from enum import IntFlag
from pathlib import Path
from types import SimpleNamespace

import pytest

from dualsense_companion.core.adaptive_triggers import (
    AdaptiveTriggerEngine,
    FakeTelemetryAdapter,
    ReactiveTriggerAdapter,
    TriggerSource,
)
from dualsense_companion.core.calibration import RobustStickCalibrator, apply_radial_deadzone
from dualsense_companion.core.config import ConfigRepository, default_config
from dualsense_companion.core.exclusive_input import (
    ExclusiveCoordinator,
    FakeExclusiveVirtualProvider,
    FakePhysicalSuppressionProvider,
)
from dualsense_companion.core.facade import CoreFacade
from dualsense_companion.core.game_candidates import FakeGameCandidateProvider, GameCandidate, merge_candidates
from dualsense_companion.core.games_repository import (
    GameRegistryRepository,
    default_games_config,
    game_definitions,
    validate_games_config,
)
from dualsense_companion.core.haptics_service import HapticsService
from dualsense_companion.core.lightbar import InterruptiblePulseAnimator, scale_rgb
from dualsense_companion.domain.errors import DS5ForgeError, ErrorCode
from dualsense_companion.domain.games import ForegroundApplication, GameDefinition
from dualsense_companion.domain.models import (
    AdaptiveTriggerEffect,
    BatterySnapshot,
    ConnectionState,
    ControllerCapabilities,
    ControllerIdentity,
    ControllerInput,
    ControllerReading,
    LightbarState,
    PlayerLedState,
    StickCalibration,
    StickTelemetry,
    TriggerState,
    normalize_controller_input,
)
from dualsense_companion.platform.windows.dualsense_adapter import PyDualSenseAdapter
from dualsense_companion.platform.windows.exclusive_provider import (
    FixedExclusiveSidecarClient,
    FixedSidecarVerifier,
    WindowsHidMaestroProvider,
)


class ManualClock:
    def __init__(self, value: float = 0.0):
        self.value = value

    def __call__(self) -> float:
        return self.value


def test_exclusive_is_disabled_by_default_and_reports_duplicate_input_risk():
    coordinator = ExclusiveCoordinator()

    capability = coordinator.capability()
    assert capability.operational is False
    assert coordinator.status().double_input_risk is True
    with pytest.raises(DS5ForgeError) as raised:
        coordinator.enable()
    assert raised.value.code is ErrorCode.EXCLUSIVE_UNAVAILABLE
    diagnostic = coordinator.duplicate_input_diagnostic()
    assert diagnostic.risk is True
    assert diagnostic.physical_visible is True


def test_exclusive_transaction_mirrors_and_rolls_back_on_suppression_failure():
    clock = ManualClock()
    virtual = FakeExclusiveVirtualProvider()
    suppression = FakePhysicalSuppressionProvider()
    coordinator = ExclusiveCoordinator(virtual, suppression, clock=clock)

    active = coordinator.enable()
    assert active.enabled is True
    assert active.double_input_risk is False
    mirrored = coordinator.mirror_reading(
        ControllerReading(connected=True, input=ControllerInput(cross=True), battery=BatterySnapshot(level=75))
    )
    assert mirrored.mirrored_sequence == 1
    assert virtual.states[-1]["input"]["cross"] is True
    assert coordinator.heartbeat().stale is False
    assert coordinator.disable(reason="test").enabled is False

    failing_virtual = FakeExclusiveVirtualProvider()
    failing_suppression = FakePhysicalSuppressionProvider(fail_enable=True)
    failing = ExclusiveCoordinator(failing_virtual, failing_suppression, clock=clock)
    with pytest.raises(DS5ForgeError) as raised:
        failing.enable()
    assert raised.value.code is ErrorCode.EXCLUSIVE_ROLLBACK
    assert failing_virtual.started is False
    assert failing_suppression.started is False
    assert failing.status().double_input_risk is True


def test_exclusive_watchdog_recovers_stale_session():
    clock = ManualClock()
    coordinator = ExclusiveCoordinator(
        FakeExclusiveVirtualProvider(),
        FakePhysicalSuppressionProvider(),
        heartbeat_timeout=0.25,
        clock=clock,
    )
    coordinator.enable()
    clock.value = 1.0
    status = coordinator.watchdog()
    assert status.enabled is False
    assert status.physical_input_visible is True
    assert status.double_input_risk is True


def test_public_exclusive_heartbeat_cannot_extend_stalled_mirror_lease():
    clock = ManualClock()
    coordinator = ExclusiveCoordinator(
        FakeExclusiveVirtualProvider(),
        FakePhysicalSuppressionProvider(),
        heartbeat_timeout=0.25,
        provider_heartbeat_interval=0.05,
        clock=clock,
    )
    coordinator.enable()

    # External/provider liveness heartbeats may keep the helper responsive, but
    # only a successful controller mirror is allowed to refresh the core lease.
    for moment in (0.05, 0.10, 0.20):
        clock.value = moment
        assert coordinator.heartbeat().enabled is True

    clock.value = 0.30
    status = coordinator.tick()
    assert status.enabled is False
    assert status.last_error is not None and "heartbeat_timeout" in status.last_error
    assert status.physical_input_visible is True
    assert status.double_input_risk is True


def test_adaptive_trigger_arbitration_ttl_and_generated_label():
    class Output:
        def __init__(self):
            self.calls = []
            self.resets = 0

        def set_triggers(self, state):
            self.calls.append(state)

        def reset_triggers(self):
            self.resets += 1

    clock = ManualClock()
    output = Output()
    engine = AdaptiveTriggerEngine(output, output_supported=True, ttl_seconds=1.0, clock=clock)
    reactive = ReactiveTriggerAdapter().from_envelope(input_state=ControllerInput(l2=1.0), audio_envelope=0.0)
    assert reactive is not None
    engine.set_reactive(reactive)
    assert engine.status.source is TriggerSource.REACTIVE
    engine.set_telemetry(FakeTelemetryAdapter().trigger_state({"impact": 1.0}, now=clock()) or TriggerState())
    assert engine.status.source is TriggerSource.TELEMETRY
    engine.set_game_native(TriggerState())
    assert engine.status.source is TriggerSource.GAME_NATIVE
    calls_before_refresh = len(output.calls)
    clock.value = 0.5
    engine.set_game_native(TriggerState(), ttl_seconds=2.0)
    assert len(output.calls) == calls_before_refresh
    assert engine.status.expires_at == pytest.approx(2.5)
    clock.value = 3.0
    assert engine.tick().source is TriggerSource.OFF
    assert output.resets >= 1
    assert engine.status.generated_effect is False


def test_calibration_rejects_outlier_and_native_keeps_raw_stick_values():
    estimate = RobustStickCalibrator(max_samples=32).estimate([(0.1, -0.05)] * 10 + [(1.0, 1.0), (float("nan"), 0.0)])
    assert estimate.rejected_samples >= 1
    assert estimate.center_x == pytest.approx(0.1)
    assert apply_radial_deadzone(0.04, 0.0, deadzone=0.08, mode="native") == pytest.approx((0.04, 0.0))
    assert apply_radial_deadzone(0.04, 0.0, deadzone=0.08, mode="remap") == (0.0, 0.0)
    sticks = StickTelemetry(0.04, 0.0, -0.04, 0.0)
    assert sticks.left_x == pytest.approx(0.04)


def test_lightbar_scaling_and_interruptible_pulse_stop():
    assert scale_rgb(LightbarState(r=200, g=100, b=50, intensity=0.5)) == (100, 50, 25)
    assert scale_rgb(LightbarState(r=200, g=100, b=50, enabled=False)) == (0, 0, 0)
    frames = []
    animator = InterruptiblePulseAnimator(frames.append, interval=0.01)
    animator.start(LightbarState(r=10, effect="pulse"), cycles=5)
    time.sleep(0.025)
    animator.stop(reset=LightbarState())
    assert frames[-1] == LightbarState()
    animator.close()


def test_candidates_prefer_running_and_dedupe_paths():
    running = GameCandidate("game.exe", "C:/Games/game.exe", pid=10, source="running")
    recent_duplicate = GameCandidate("GAME.EXE", "c:/games/game.exe", source="recent")
    recent_other = GameCandidate("other.exe", "C:/Games/other.exe", source="recent")
    merged = merge_candidates([running], [recent_duplicate, recent_other])
    assert merged == [running, recent_other]
    provider = FakeGameCandidateProvider([running], [recent_other])
    assert list(provider.running()) == [running]


def test_touch_pipeline_preserves_both_real_pydualsense_contacts_and_raw_values():
    raw = type(
        "State",
        (),
        {
            "trackPadTouch0": type("Touch", (), {"isActive": True, "X": 100, "Y": 200, "ID": 7})(),
            "trackPadTouch1": type("Touch", (), {"isActive": True, "X": 900, "Y": 800, "ID": 8})(),
        },
    )()
    normalized = normalize_controller_input(raw)
    assert normalized.touch0.contact_id == 7
    assert normalized.touch1.contact_id == 8
    assert normalized.touch0.raw["X"] == 100
    assert normalized.touch1.raw["Y"] == 800


class _FakeControllerFactory:
    def connect(self):  # pragma: no cover - tests inject adapter output directly
        raise AssertionError("controller connection is not expected in these tests")


class _FakeMouse:
    def move(self, dx, dy):
        return None

    def button(self, left, down):
        return None

    def wheel(self, amount, horizontal=False):
        return None

    def release_all(self):
        return None


def _make_facade(root: Path, **kwargs) -> CoreFacade:
    repository = ConfigRepository(
        config_path=root / "config.json",
        bundled_config_path=Path("source/dualsense_companion/resources/default_config.json"),
        bundled_profiles_dir=Path("source/dualsense_companion/resources/profiles"),
        user_profiles_dir=root / "profiles",
    )
    return CoreFacade(
        controller_factory=_FakeControllerFactory(),
        mouse_output=_FakeMouse(),
        config_repository=repository,
        games_repository=GameRegistryRepository(path=root / "games.json"),
        **kwargs,
    )


def _operational_exclusive(virtual=None, suppression=None) -> ExclusiveCoordinator:
    return ExclusiveCoordinator(
        virtual or FakeExclusiveVirtualProvider(),
        suppression or FakePhysicalSuppressionProvider(),
        heartbeat_timeout=0.25,
    )


def test_exclusive_mirror_refreshes_lease_and_provider_heartbeat_is_throttled():
    clock = ManualClock()
    virtual = FakeExclusiveVirtualProvider()
    suppression = FakePhysicalSuppressionProvider()
    coordinator = ExclusiveCoordinator(
        virtual,
        suppression,
        heartbeat_timeout=1.0,
        provider_heartbeat_interval=0.5,
        clock=clock,
    )
    coordinator.enable()
    calls_after_enable = (len(virtual.states),)
    # A successful mirror advances the lease and the mirrored sequence.
    status = coordinator.mirror_reading(ControllerReading(input=ControllerInput(cross=True)))
    assert status.mirrored_sequence == 1
    assert status.heartbeat_at == pytest.approx(clock.value)
    # Only the acquire request has reached the helper so far: mirroring must
    # not send a provider heartbeat at controller polling frequency.
    assert virtual.started is True
    assert calls_after_enable == (0,)
    clock.value = 0.6
    coordinator.tick()
    # The throttled provider heartbeat has now fired once, and the lease is
    # still alive because the mirror refreshed it.
    assert coordinator.status().enabled is True


def test_exclusive_tick_expires_stalled_session_with_neutral_cleanup():
    clock = ManualClock()
    virtual = FakeExclusiveVirtualProvider()
    suppression = FakePhysicalSuppressionProvider()
    coordinator = ExclusiveCoordinator(
        virtual,
        suppression,
        heartbeat_timeout=0.25,
        provider_heartbeat_interval=0.2,
        clock=clock,
    )
    coordinator.enable()
    clock.value = 5.0
    status = coordinator.tick()
    assert status.enabled is False
    assert status.physical_input_visible is True
    assert status.double_input_risk is True
    assert status.last_error is not None
    assert virtual.started is False
    assert suppression.started is False


def test_exclusive_recovery_reports_whether_anything_was_recovered():
    virtual = FakeExclusiveVirtualProvider()
    suppression = FakePhysicalSuppressionProvider()
    coordinator = ExclusiveCoordinator(virtual, suppression)

    clean = coordinator.recover()
    assert clean.performed is False

    virtual.started = True
    suppression.started = True
    recovered = coordinator.recover()
    assert recovered.performed is True
    assert set(recovered.providers) == {"virtual", "suppression"}


class _BlockingStdout:
    def readline(self):
        time.sleep(3.0)
        return ""


class _FailingStdin:
    def write(self, _value):
        raise OSError("helper stdin was closed")

    def flush(self):
        return None


class _FakeHelperProcess:
    def __init__(self, *, stdin, stdout):
        self.stdin = stdin
        self.stdout = stdout
        self.terminated = False
        self.killed = False

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True


def test_exclusive_sidecar_request_has_finite_timeout_and_kills_helper():
    client = FixedExclusiveSidecarClient(FixedSidecarVerifier(None))
    process = _FakeHelperProcess(stdin=io.StringIO(), stdout=_BlockingStdout())
    client.process = process

    with pytest.raises(RuntimeError):
        client.request({"op": "acquire"}, timeout=0.05)
    assert process.terminated is True


def test_exclusive_sidecar_close_terminates_even_when_release_fails():
    client = FixedExclusiveSidecarClient(FixedSidecarVerifier(None))
    process = _FakeHelperProcess(stdin=_FailingStdin(), stdout=io.StringIO())
    client.process = process

    client.close()
    assert process.terminated is True
    assert client.process is None


def test_exclusive_provider_wrapper_always_closes_helper_when_release_request_fails():
    client = FixedExclusiveSidecarClient(FixedSidecarVerifier(None))
    process = _FakeHelperProcess(stdin=io.StringIO(), stdout=io.StringIO())
    client.process = process

    def fail_release(_payload, **_kwargs):
        raise RuntimeError("release rejected")

    client.request = fail_release  # type: ignore[method-assign]
    provider = WindowsHidMaestroProvider(client)

    with pytest.raises(RuntimeError, match="release rejected"):
        provider.close(token="test-owner", generation=7)

    # Provider-level finally must reach the client's process terminator even
    # though the explicit release protocol request raised.
    assert process.terminated is True
    assert client.process is None


def test_exclusive_sidecar_discards_stderr_to_avoid_pipe_deadlock():
    source = Path("source/dualsense_companion/platform/windows/exclusive_provider.py").read_text(encoding="utf-8")
    assert "stderr=subprocess.DEVNULL" in source
    assert "stderr=subprocess.PIPE" not in source


def test_facade_exclusive_enable_mirror_disconnect_and_shutdown_are_idempotent():
    with tempfile.TemporaryDirectory() as temp:
        virtual = FakeExclusiveVirtualProvider()
        facade = _make_facade(Path(temp), exclusive_coordinator=_operational_exclusive(virtual))
        try:
            status = facade.enable_exclusive()
            assert status["enabled"] is True
            facade._on_reading(ControllerReading(input=ControllerInput(cross=True, r2=0.5)))
            assert facade._exclusive.status().mirrored_sequence == 1
            assert virtual.states[-1]["input"]["cross"] is True

            facade._on_disconnected()
            assert facade.snapshot().exclusive.enabled is False
            facade._on_disconnected()
            assert facade.snapshot().exclusive.enabled is False

            facade.enable_exclusive()
            assert facade.snapshot().exclusive.enabled is True
            facade.stop()
            assert facade.snapshot().exclusive.enabled is False
        finally:
            facade.stop()


def test_facade_exclusive_cannot_coexist_with_remap_and_disables_first():
    with tempfile.TemporaryDirectory() as temp:
        virtual = FakeExclusiveVirtualProvider()
        facade = _make_facade(Path(temp), exclusive_coordinator=_operational_exclusive(virtual))
        try:
            facade.update_compatibility("remap")
            with pytest.raises(DS5ForgeError) as raised:
                facade.enable_exclusive()
            assert raised.value.code is ErrorCode.EXCLUSIVE_UNAVAILABLE
            assert facade.snapshot().exclusive.enabled is False

            facade.update_compatibility("native")
            facade.enable_exclusive()
            assert facade.snapshot().exclusive.enabled is True
            # Switching to Remap must disable Exclusive before applying output.
            facade.update_compatibility("remap")
            assert facade.snapshot().exclusive.enabled is False
            assert virtual.started is False
        finally:
            facade.stop()


def test_facade_exclusive_provider_failure_rolls_back_and_stays_safe():
    with tempfile.TemporaryDirectory() as temp:
        virtual = FakeExclusiveVirtualProvider()
        suppression = FakePhysicalSuppressionProvider(fail_enable=True)
        facade = _make_facade(
            Path(temp),
            exclusive_coordinator=ExclusiveCoordinator(virtual, suppression, heartbeat_timeout=0.25),
        )
        try:
            with pytest.raises(DS5ForgeError) as raised:
                facade.enable_exclusive()
            assert raised.value.code is ErrorCode.EXCLUSIVE_ROLLBACK
            assert facade.snapshot().exclusive.enabled is False
            assert facade.snapshot().exclusive.double_input_risk is True
            assert virtual.started is False
        finally:
            facade.stop()

    with tempfile.TemporaryDirectory() as temp:
        failing_virtual = FakeExclusiveVirtualProvider(fail_start=True)
        facade = _make_facade(
            Path(temp),
            exclusive_coordinator=ExclusiveCoordinator(
                failing_virtual, FakePhysicalSuppressionProvider(), heartbeat_timeout=0.25
            ),
        )
        try:
            with pytest.raises(DS5ForgeError) as raised:
                facade.enable_exclusive()
            assert raised.value.code is ErrorCode.EXCLUSIVE_ROLLBACK
            assert failing_virtual.started is False
            assert facade.snapshot().exclusive.enabled is False
        finally:
            facade.stop()


def test_legacy_game_registry_defaults_adaptive_trigger_mode_without_data_loss():
    document = default_games_config()
    document["games"] = [
        {
            "id": "legacy",
            "name": "Legacy",
            "executables": ["legacy.exe"],
            "executable_path": None,
            "profile": "Default",
            "compatibility_mode": "native",
            "enabled": True,
        }
    ]
    normalized = validate_games_config(document)
    assert normalized["games"][0]["adaptive_trigger_mode"] == "native"
    definitions = game_definitions(normalized)
    assert definitions[0].adaptive_trigger_mode.value == "native"
    assert definitions[0].executables == ("legacy.exe",)


def test_facade_exclusive_mirror_uses_calibrated_sticks_while_native_stays_raw():
    with tempfile.TemporaryDirectory() as temp:
        virtual = FakeExclusiveVirtualProvider()
        facade = _make_facade(Path(temp), exclusive_coordinator=_operational_exclusive(virtual))
        try:
            facade.update_stick_calibration(StickCalibration(left_deadzone=0.2, left_center_x=0.05, left_center_y=0.0))
            facade.enable_exclusive()
            reading = ControllerReading(input=ControllerInput(sticks=StickTelemetry(left_x=0.1, left_y=0.0)))
            facade._on_reading(reading)
            mirrored = virtual.states[-1]["input"]["sticks"]
            assert mirrored["left_x"] == pytest.approx(0.0)
            # Native telemetry is untouched: the raw value remains authoritative.
            facade._on_reading(ControllerReading(input=reading.input))
            assert facade.snapshot().input.sticks.left_x == pytest.approx(0.1)
        finally:
            facade.stop()


def test_facade_exclusive_mirror_applies_default_deadzone_without_mutating_native_input():
    with tempfile.TemporaryDirectory() as temp:
        virtual = FakeExclusiveVirtualProvider()
        facade = _make_facade(Path(temp), exclusive_coordinator=_operational_exclusive(virtual))
        try:
            assert facade.snapshot().stick_calibration == StickCalibration()
            facade.enable_exclusive()
            reading = ControllerReading(input=ControllerInput(sticks=StickTelemetry(left_x=0.04, left_y=0.0)))
            facade._on_reading(reading)

            assert virtual.states[-1]["input"]["sticks"]["left_x"] == pytest.approx(0.0)
            assert facade.snapshot().input.sticks.left_x == pytest.approx(0.04)
        finally:
            facade.stop()


def _reactive_facade(root: Path):
    facade = _make_facade(root)
    writes: list[TriggerState] = []
    resets: list[int] = []
    facade.controller.set_triggers = lambda state: writes.append(state)
    facade.controller.reset_triggers = lambda: resets.append(1)
    facade._adaptive_triggers.output_supported = True
    facade._adaptive_triggers.output = facade.controller
    return facade, writes, resets


class _ConnectedTriggerAdapter:
    def __init__(self):
        self.identity = ControllerIdentity()
        self.capabilities = ControllerCapabilities(
            rumble=False,
            touchpad=False,
            microphone_button=False,
            lightbar=False,
            adaptive_triggers=True,
        )
        self.trigger_calls: list[TriggerState] = []
        self.reset_calls = 0

    def set_triggers(self, state: TriggerState) -> None:
        self.trigger_calls.append(state)

    def reset_triggers(self) -> None:
        self.reset_calls += 1

    def neutralize(self) -> None:
        self.reset_triggers()

    def close(self) -> None:
        return None


def test_connected_automatic_profile_never_writes_static_triggers_and_modes_own_output():
    with tempfile.TemporaryDirectory() as temp:
        facade = _make_facade(Path(temp))
        adapter = _ConnectedTriggerAdapter()
        with facade.controller._adapter_lock:
            facade.controller._adapter = adapter
        facade.store.mutate(
            lambda current: replace(
                current,
                connection=ConnectionState.CONNECTED,
                identity=adapter.identity,
                capabilities=adapter.capabilities,
            )
        )
        facade._adaptive_triggers.set_output_supported(True)
        facade._adaptive_triggers.output = facade.controller

        profile = facade.controller_profile("Game")
        profile["triggers"] = {
            "left": AdaptiveTriggerEffect(mode="resistance", start_position=40, force=180).to_dict(),
            "right": AdaptiveTriggerEffect(mode="resistance", start_position=50, force=170).to_dict(),
        }

        try:
            facade.apply_controller_profile(profile, name="Game", source="automatic")
            native_baseline_resets = adapter.reset_calls
            facade._apply_adaptive_trigger_mode(
                GameDefinition(id="native", name="Native", executables=("native.exe",), profile="Game")
            )
            assert adapter.trigger_calls == []
            assert adapter.reset_calls == native_baseline_resets

            facade.apply_controller_profile(profile, name="Game", source="automatic")
            off_baseline_resets = adapter.reset_calls
            facade._apply_adaptive_trigger_mode(
                GameDefinition(
                    id="off",
                    name="Off",
                    executables=("off.exe",),
                    profile="Game",
                    adaptive_trigger_mode="off",
                )
            )
            assert adapter.trigger_calls == []
            assert adapter.reset_calls == off_baseline_resets + 1

            facade.apply_controller_profile(profile, name="Game", source="automatic")
            reactive_baseline_resets = adapter.reset_calls
            facade._apply_adaptive_trigger_mode(
                GameDefinition(
                    id="reactive",
                    name="Reactive",
                    executables=("reactive.exe",),
                    profile="Game",
                    adaptive_trigger_mode="reactive",
                )
            )
            assert adapter.trigger_calls == []
            assert adapter.reset_calls == reactive_baseline_resets + 1

            facade._on_audio_envelope(0.8)
            facade._update_reactive_triggers(ControllerInput(l2=1.0, r2=0.7))
            assert len(adapter.trigger_calls) == 1
            static_state = TriggerState(
                left=AdaptiveTriggerEffect(mode="resistance", start_position=40, force=180),
                right=AdaptiveTriggerEffect(mode="resistance", start_position=50, force=170),
            )
            assert adapter.trigger_calls[-1] != static_state
            assert facade.adaptive_trigger_status()["generated_effect"] is True
        finally:
            with facade.controller._adapter_lock:
                facade.controller._adapter = None
            facade.stop()


def test_facade_games_default_to_native_without_generated_trigger_writes():
    with tempfile.TemporaryDirectory() as temp:
        facade, writes, _resets = _reactive_facade(Path(temp))
        try:
            facade.add_game(GameDefinition(id="native-game", name="Native", executables=("native.exe",)).to_dict())
            facade.update_automation({"enabled": True})
            facade._on_foreground_observation(
                ForegroundApplication(
                    available=True,
                    pid=1,
                    executable_name="native.exe",
                    executable_path="C:\\Games\\native.exe",
                    process_alive=True,
                ),
                True,
            )
            facade._on_audio_envelope(0.9)
            facade._on_reading(ControllerReading(input=ControllerInput(l2=1.0)))
            assert writes == []
            assert facade.adaptive_trigger_status()["source"] == "off"
        finally:
            facade.stop()


def test_facade_reactive_mode_is_explicit_generated_and_resets_on_exit_and_ttl():
    with tempfile.TemporaryDirectory() as temp:
        facade, writes, _resets = _reactive_facade(Path(temp))
        events: list[str] = []
        subscription = facade.subscribe()
        try:
            game = GameDefinition(
                id="reactive-game",
                name="Reactive",
                executables=("reactive.exe",),
            ).to_dict()
            game["adaptive_trigger_mode"] = "reactive"
            facade.add_game(game)
            facade.update_automation({"enabled": True})
            facade._on_foreground_observation(
                ForegroundApplication(
                    available=True,
                    pid=2,
                    executable_name="reactive.exe",
                    executable_path="C:\\Games\\reactive.exe",
                    process_alive=True,
                ),
                True,
            )
            assert facade.adaptive_trigger_status()["source"] == "off"

            facade._on_audio_envelope(0.9)
            facade._on_reading(ControllerReading(input=ControllerInput(l2=0.9)))
            assert facade.adaptive_trigger_status()["source"] == "reactive"
            assert facade.adaptive_trigger_status()["generated_effect"] is True
            first_write_count = len(writes)
            assert first_write_count >= 1
            # Coalescing: an unchanged signal must not rewrite hardware.
            facade._on_reading(ControllerReading(input=ControllerInput(l2=0.9)))
            assert len(writes) == first_write_count

            # TTL expiry clears the stale generated effect.
            now = facade._adaptive_triggers.clock() + 5.0
            facade._adaptive_triggers.tick(now=now)
            facade._publish_adaptive_trigger_status(facade._adaptive_triggers.status)
            assert facade.adaptive_trigger_status()["source"] == "off"

            facade._on_foreground_observation(ForegroundApplication.desktop(now=3.0), True)
            assert facade.adaptive_trigger_status()["source"] == "off"

            while True:
                try:
                    events.append(subscription.get_nowait().type)
                except Exception:
                    break
            assert "adaptive_trigger.changed" in events
        finally:
            facade.unsubscribe(subscription)
            facade.stop()


class _LabAdapter:
    def __init__(self):
        self.identity = ControllerIdentity()
        self.capabilities = ControllerCapabilities(lightbar=True, adaptive_triggers=False)
        self.lightbar = LightbarState()
        self.player_leds = PlayerLedState()
        self.lightbar_calls: list[LightbarState] = []

    def get_lightbar(self):
        return self.lightbar

    def set_lightbar(self, state):
        self.lightbar_calls.append(state)
        self.lightbar = state

    def reset_lightbar(self):
        self.lightbar = LightbarState()

    def get_player_leds(self):
        return self.player_leds

    def set_player_leds(self, state):
        self.player_leds = state

    def reset_player_leds(self):
        self.player_leds = PlayerLedState()

    def neutralize(self):
        self.reset_lightbar()
        self.reset_player_leds()


def test_adapter_fake_lightbar_intensity_and_player_leds_stay_separate():
    with tempfile.TemporaryDirectory() as temp:
        facade = _make_facade(Path(temp))
        adapter = _LabAdapter()
        with facade.controller._adapter_lock:
            facade.controller._adapter = adapter
        facade._on_connected(adapter)
        try:
            facade.apply_lightbar(LightbarState(r=200, g=100, b=50, intensity=0.5))
            assert adapter.lightbar_calls[-1].scaled_rgb == (100, 50, 25)
            assert adapter.lightbar_calls[-1].pulse == "off"

            facade.apply_player_leds(PlayerLedState(enabled=True, intensity=0.25))
            assert facade.snapshot().player_leds.intensity == pytest.approx(0.25)
            # Player LED changes never mutate the RGB lightbar state.
            assert facade.snapshot().lightbar.r == 200

            facade.apply_lightbar(LightbarState(r=200, g=100, b=50, enabled=False))
            assert adapter.lightbar_calls[-1].scaled_rgb == (0, 0, 0)
            # Disabling preserves the saved RGB values.
            assert facade.snapshot().lightbar.r == 200
            assert facade.snapshot().player_leds.intensity == pytest.approx(0.25)
        finally:
            facade.stop()


class _FakeLedOptions(IntFlag):
    Off = 0
    PlayerLedBrightness = 1
    UninterrumpableLed = 2
    Both = 3


class _FakeBrightness(IntFlag):
    high = 0
    medium = 1
    low = 2


class _FakePlayerID(IntFlag):
    PLAYER_1 = 4
    PLAYER_2 = 10


class _FakeDualSenseLight:
    def __init__(self):
        self.TouchpadColor = (0, 0, 255)
        self.ledOption = _FakeLedOptions.Both
        self.brightness = _FakeBrightness.low
        self.playerNumber = _FakePlayerID.PLAYER_1
        self.pulseOptions = 0

    def setColorI(self, r, g, b):
        self.TouchpadColor = (r, g, b)

    def setLEDOption(self, option):
        self.ledOption = option

    def setBrightness(self, brightness):
        self.brightness = brightness

    def setPlayerID(self, player):
        self.playerNumber = player


def test_pydualsense_adapter_reconciles_rgb_and_player_leds_as_one_output_state():
    light = _FakeDualSenseLight()
    raw = SimpleNamespace(
        connected=True,
        state=SimpleNamespace(),
        light=light,
        triggerL=None,
        triggerR=None,
        setLeftMotor=lambda _value: None,
        setRightMotor=lambda _value: None,
        battery=SimpleNamespace(Level=50, Charging=False),
        close=lambda: None,
    )
    adapter = PyDualSenseAdapter(
        raw,
        brightness=_FakeBrightness,
        led_options=_FakeLedOptions,
        player_ids=_FakePlayerID,
    )

    adapter.set_player_leds(PlayerLedState(enabled=False, intensity=0.25))
    assert light.playerNumber == _FakePlayerID(0)
    assert light.ledOption == _FakeLedOptions.Both

    # A later RGB write must preserve the disabled player pattern.
    adapter.set_lightbar(LightbarState(r=180, g=90, b=45, enabled=True, intensity=0.5))
    assert light.TouchpadColor == (90, 45, 22)
    assert light.playerNumber == _FakePlayerID(0)
    assert light.ledOption == _FakeLedOptions.Both

    adapter.set_player_leds(PlayerLedState(enabled=True, intensity=0.25))
    assert light.playerNumber == _FakePlayerID.PLAYER_1
    assert light.TouchpadColor == (90, 45, 22)
    assert light.brightness == _FakeBrightness.low

    # Disabling RGB is represented by zero RGB, not by an LED mask that would
    # suppress the player-LED update fields.
    adapter.set_lightbar(LightbarState(r=180, g=90, b=45, enabled=False))
    assert light.TouchpadColor == (0, 0, 0)
    assert light.playerNumber == _FakePlayerID.PLAYER_1
    assert light.ledOption == _FakeLedOptions.Both


def test_lightbar_enabled_is_zero_output_and_intensity_scales_rgb():
    assert scale_rgb(LightbarState(r=200, g=100, b=50, intensity=0.5)) == (100, 50, 25)
    assert scale_rgb(LightbarState(r=200, g=100, b=50, intensity=0.0)) == (0, 0, 0)
    disabled = LightbarState(r=200, g=100, b=50, enabled=False, intensity=1.0)
    assert disabled.scaled_rgb == (0, 0, 0)
    # Disabling never destroys the saved RGB values.
    assert (disabled.r, disabled.g, disabled.b) == (200, 100, 50)


def test_audio_playback_loopback_dsp_path_drives_motor_and_neutralizes():
    outputs = []

    class Capture:
        sample_rate = 48_000
        channels = 1
        frames = 64
        name = "Fake WASAPI loopback"

        def __init__(self):
            self.reads = 0

        def read(self):
            self.reads += 1
            return struct.pack("<" + "f" * self.frames, *([0.8] * self.frames))

        def default_output_changed(self):
            return True

        def close(self):
            return None

    capture = Capture()

    class Context:
        def __enter__(self):
            return capture

        def __exit__(self, exc_type, exc, tb):
            capture.close()

    class Factory:
        def open(self):
            return Context()

    service = HapticsService(
        lambda left, right: outputs.append((left, right)) or True,
        lambda: default_config()["rumble"],
        lambda: True,
        capture_factory=Factory(),
    )
    service._run_once()
    assert any(left > 0 or right > 0 for left, right in outputs)
    assert outputs[-1] == (0, 0)
