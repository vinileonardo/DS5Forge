import tempfile
import time
import unittest
from pathlib import Path

from dualsense_companion.core.config import ConfigRepository, default_controller_profile
from dualsense_companion.core.controller_service import LifecycleNotification
from dualsense_companion.core.facade import CoreFacade
from dualsense_companion.domain.errors import DS5ForgeError, ErrorCode
from dualsense_companion.domain.models import (
    AdaptiveTriggerEffect,
    ConnectionState,
    ControllerCapabilities,
    ControllerIdentity,
    LightbarState,
    TriggerState,
)


class FakeMouse:
    def move(self, _dx, _dy):
        return None

    def button(self, _left, _down):
        return None

    def wheel(self, _amount, horizontal=False):
        return None

    def release_all(self):
        return None


class FakeFactory:
    def connect(self):
        raise AssertionError("the lifecycle worker is not used in this test")


class LabAdapter:
    identity = ControllerIdentity(model="Lab DualSense")
    capabilities = ControllerCapabilities(
        rumble=True,
        touchpad=True,
        microphone_button=True,
        lightbar=True,
        adaptive_triggers=True,
    )

    def __init__(self):
        self.lightbar = LightbarState()
        self.triggers = TriggerState()
        self.lightbar_calls = []
        self.trigger_calls = []
        self.motor_calls = []
        self.fail_triggers = False
        self.fail_lightbar = False

    def is_connected(self):
        return True

    def read(self):
        raise AssertionError("read is not expected")

    def set_motors(self, left, right):
        self.motor_calls.append((left, right))

    def neutralize(self):
        self.set_motors(0, 0)
        self.reset_triggers()

    def startup_feedback(self):
        return None

    def close(self):
        return None

    def get_lightbar(self):
        return self.lightbar

    def set_lightbar(self, state):
        if self.fail_lightbar and state != LightbarState():
            raise DS5ForgeError(ErrorCode.LIGHTBAR_OUTPUT_FAILED, "lightbar write failed")
        self.lightbar_calls.append(state)
        self.lightbar = state

    def reset_lightbar(self):
        self.set_lightbar(LightbarState())

    def set_triggers(self, state):
        if self.fail_triggers:
            raise DS5ForgeError(ErrorCode.TRIGGER_OUTPUT_FAILED, "trigger write failed")
        self.trigger_calls.append(state)
        self.triggers = state

    def reset_triggers(self):
        self.trigger_calls.append(TriggerState())
        self.triggers = TriggerState()


class NoRumbleAdapter(LabAdapter):
    capabilities = ControllerCapabilities(
        usb=True,
        rumble=False,
        touchpad=True,
        microphone_button=True,
        lightbar=True,
        adaptive_triggers=True,
    )


class FacadeControllerLabTests(unittest.TestCase):
    def make_facade(self, root):
        repo = ConfigRepository(
            config_path=root / "config.json",
            bundled_config_path=Path("source/dualsense_companion/resources/default_config.json"),
            bundled_profiles_dir=Path("source/dualsense_companion/resources/profiles"),
            user_profiles_dir=root / "profiles",
        )
        return CoreFacade(config_repository=repo, controller_factory=FakeFactory(), mouse_output=FakeMouse())

    @staticmethod
    def attach(facade, adapter):
        with facade.controller._adapter_lock:
            facade.controller._adapter = adapter
        facade._on_connected(adapter)

    @staticmethod
    def mark_connected(facade):
        facade._on_lifecycle(LifecycleNotification(ConnectionState.CONNECTED))

    @staticmethod
    def mark_running(facade):
        # The lifecycle worker is not started in these unit tests; mark the
        # facade as running so audio pause/resume coordination is exercised.
        facade._started = True

    def test_lightbar_trigger_preview_and_haptics_are_owned_by_facade(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = self.make_facade(Path(temp))
            adapter = LabAdapter()
            try:
                self.attach(facade, adapter)
                self.mark_connected(facade)
                applied = facade.apply_lightbar(LightbarState(20, 30, 40))
                self.assertEqual(applied.r, 20)

                preview = facade.preview_triggers(TriggerState(), duration_ms=20)
                self.assertEqual(preview.status, "running")
                time.sleep(0.08)
                self.assertEqual(facade.snapshot().triggers.preview.status, "timed_out")

                run = facade.start_haptics_test(left=40, right=30, duration_ms=20)
                self.assertEqual(run.status, "running")
                time.sleep(0.08)
                self.assertEqual(facade.snapshot().haptics_test.status, "completed")
                self.assertIn((0, 0), adapter.motor_calls)
            finally:
                facade.stop()

    def test_profile_hardware_failure_rolls_back_outputs_before_raising(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = self.make_facade(Path(temp))
            adapter = LabAdapter()
            try:
                self.attach(facade, adapter)
                self.mark_connected(facade)
                facade.apply_lightbar(LightbarState(10, 20, 30))
                facade.configure_triggers(TriggerState(left=AdaptiveTriggerEffect(mode="rigid", force=77)))
                self.assertNotEqual(facade.snapshot().lightbar, LightbarState())
                self.assertEqual(facade.snapshot().triggers.left.mode, "rigid")
                adapter.fail_triggers = True

                profile = default_controller_profile("Broken")
                profile["lightbar"] = {"r": 210, "g": 10, "b": 10, "enabled": True, "brightness": 2, "pulse": "off"}
                with self.assertRaises(DS5ForgeError):
                    facade.apply_controller_profile(profile)
                self.assertEqual(adapter.lightbar, LightbarState())
                self.assertEqual(adapter.triggers, TriggerState())
                self.assertGreaterEqual(len(adapter.trigger_calls), 1)
                # The authoritative snapshot must match the neutralized
                # hardware instead of the pre-failure output state.
                self.assertEqual(facade.snapshot().lightbar, LightbarState())
                self.assertEqual(facade.snapshot().triggers.left.mode, "off")
                self.assertEqual(facade.snapshot().triggers.right.mode, "off")
            finally:
                facade.stop()

    def test_failed_lightbar_apply_reports_neutral_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = self.make_facade(Path(temp))
            adapter = LabAdapter()
            try:
                self.attach(facade, adapter)
                self.mark_connected(facade)
                facade.apply_lightbar(LightbarState(10, 20, 30))
                self.assertNotEqual(facade.snapshot().lightbar, LightbarState())
                adapter.fail_lightbar = True

                with self.assertRaises(DS5ForgeError):
                    facade.apply_lightbar(LightbarState(200, 10, 10))

                self.assertEqual(adapter.lightbar, LightbarState())
                self.assertEqual(facade.snapshot().lightbar, LightbarState())
            finally:
                facade.stop()

    def test_failed_trigger_configure_reports_neutral_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = self.make_facade(Path(temp))
            adapter = LabAdapter()
            try:
                self.attach(facade, adapter)
                self.mark_connected(facade)
                facade.configure_triggers(TriggerState(left=AdaptiveTriggerEffect(mode="rigid", force=99)))
                self.assertEqual(facade.snapshot().triggers.left.mode, "rigid")
                adapter.fail_triggers = True

                with self.assertRaises(DS5ForgeError):
                    facade.configure_triggers(TriggerState(left=AdaptiveTriggerEffect(mode="pulse", force=50)))

                self.assertEqual(adapter.triggers, TriggerState())
                self.assertEqual(facade.snapshot().triggers.left.mode, "off")
            finally:
                facade.stop()

    def test_connected_rumble_test_requires_rumble_capability(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = self.make_facade(Path(temp))
            adapter = NoRumbleAdapter()
            try:
                self.attach(facade, adapter)
                self.mark_connected(facade)

                self.assertFalse(facade.snapshot().capabilities.rumble)
                with self.assertRaises(DS5ForgeError) as raised:
                    facade.test_rumble()
                self.assertEqual(raised.exception.code, ErrorCode.CAPABILITY_UNSUPPORTED)
                self.assertEqual(adapter.motor_calls, [])
            finally:
                facade.stop()

    def test_duplicate_haptics_test_does_not_resume_audio_during_active_run(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = self.make_facade(Path(temp))
            adapter = LabAdapter()
            try:
                self.attach(facade, adapter)
                self.mark_connected(facade)
                self.mark_running(facade)
                facade.start_haptics_test(left=50, right=40, duration_ms=5_000)
                self.assertIsNone(facade._haptics)
                self.assertEqual(facade._haptics_bench.run.status, "running")

                with self.assertRaises(DS5ForgeError) as raised:
                    facade.start_haptics_test(left=10, right=10, duration_ms=5_000)
                self.assertEqual(raised.exception.code, ErrorCode.HAPTICS_TEST_BUSY)
                self.assertEqual(facade._haptics_bench.run.status, "running")
                self.assertIsNone(facade._haptics)
            finally:
                facade.stop()

    def test_cancelled_haptics_test_resumes_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = self.make_facade(Path(temp))
            adapter = LabAdapter()
            try:
                self.attach(facade, adapter)
                self.mark_connected(facade)
                self.mark_running(facade)
                facade.start_haptics_test(left=50, right=40, duration_ms=5_000)
                self.assertIsNone(facade._haptics)

                facade.cancel_haptics_test()

                self.assertIsNotNone(facade._haptics)
            finally:
                facade.stop()

    def test_haptics_test_neutralization_preserves_adaptive_triggers(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = self.make_facade(Path(temp))
            adapter = LabAdapter()
            try:
                self.attach(facade, adapter)
                self.mark_connected(facade)
                self.mark_running(facade)
                effect = TriggerState(left=AdaptiveTriggerEffect(mode="rigid", force=99))
                facade.configure_triggers(effect)
                self.assertEqual(adapter.triggers.left.force, 99)

                facade.start_haptics_test(left=40, right=30, duration_ms=20)
                time.sleep(0.08)

                self.assertEqual(facade.snapshot().haptics_test.status, "completed")
                self.assertEqual(adapter.triggers.left.mode, "rigid")
                self.assertEqual(adapter.triggers.left.force, 99)
            finally:
                facade.stop()

    def test_disabling_rumble_does_not_reset_adaptive_triggers(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = self.make_facade(Path(temp))
            adapter = LabAdapter()
            try:
                self.attach(facade, adapter)
                self.mark_connected(facade)
                effect = TriggerState(left=AdaptiveTriggerEffect(mode="rigid", force=99))
                facade.configure_triggers(effect)

                facade.set_rumble_enabled(False)

                self.assertEqual(adapter.triggers.left.mode, "rigid")
                self.assertEqual(adapter.triggers.left.force, 99)
                self.assertEqual(facade.snapshot().motors.left, 0)
            finally:
                facade.stop()

    def test_trigger_preview_event_reports_the_previewed_effect(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = self.make_facade(Path(temp))
            adapter = LabAdapter()
            try:
                self.attach(facade, adapter)
                self.mark_connected(facade)
                events = []
                original = facade.store.publish

                def capture(event_type, payload):
                    events.append((event_type, payload))
                    return original(event_type, payload)

                facade.store.publish = capture
                facade.preview_triggers(
                    TriggerState(left=AdaptiveTriggerEffect(mode="rigid", force=11)),
                    duration_ms=5_000,
                )
                facade.cancel_trigger_preview()
                events.clear()

                facade.preview_triggers(
                    TriggerState(left=AdaptiveTriggerEffect(mode="rigid", force=222)),
                    duration_ms=5_000,
                )
                previews = [
                    payload
                    for event_type, payload in events
                    if event_type == "controller.lab" and payload.get("kind") == "triggers.preview"
                ]
                self.assertTrue(previews)
                self.assertEqual(previews[-1]["state"]["left"]["force"], 222)
                self.assertEqual(previews[-1]["preview"].status, "running")
            finally:
                facade.stop()


if __name__ == "__main__":
    unittest.main()
