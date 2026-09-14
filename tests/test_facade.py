import tempfile
import unittest
from pathlib import Path

from dualsense_companion.core.config import ConfigRepository
from dualsense_companion.core.controller_service import LifecycleNotification
from dualsense_companion.core.facade import CoreFacade
from dualsense_companion.domain.errors import ControllerUnavailableError
from dualsense_companion.domain.models import BatterySnapshot, ConnectionState, ControllerReading


class FakeControllerFactory:
    def connect(self):
        raise AssertionError("controller connection is not expected in facade unit tests")


class FakeMouse:
    def move(self, dx, dy):
        return None

    def button(self, left, down):
        return None

    def wheel(self, amount, horizontal=False):
        return None

    def release_all(self):
        return None


class FacadeTests(unittest.TestCase):
    def make_repo(self, root: Path) -> ConfigRepository:
        return ConfigRepository(
            config_path=root / "config.json",
            bundled_config_path=Path("source/dualsense_companion/resources/default_config.json"),
            bundled_profiles_dir=Path("source/dualsense_companion/resources/profiles"),
            user_profiles_dir=root / "profiles",
        )

    def test_unchanged_battery_does_not_flood_state_events_at_input_poll_rate(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = CoreFacade(
                config_repository=self.make_repo(Path(temp)),
                controller_factory=FakeControllerFactory(),
                mouse_output=FakeMouse(),
            )
            initial_sequence = facade.snapshot().sequence
            facade._on_reading(ControllerReading(battery=BatterySnapshot(level=0)))
            self.assertEqual(facade.snapshot().sequence, initial_sequence)

            facade._on_reading(ControllerReading(battery=BatterySnapshot(level=20)))
            changed_sequence = facade.snapshot().sequence
            self.assertGreater(changed_sequence, initial_sequence)
            facade._on_reading(ControllerReading(battery=BatterySnapshot(level=20)))
            self.assertEqual(facade.snapshot().sequence, changed_sequence)

    def test_missing_usb_controller_is_waiting_not_degraded(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = CoreFacade(
                config_repository=self.make_repo(Path(temp)),
                controller_factory=FakeControllerFactory(),
                mouse_output=FakeMouse(),
            )
            facade._on_lifecycle(LifecycleNotification(ConnectionState.DISCONNECTED, ControllerUnavailableError()))

            self.assertEqual(facade.health_dict()["status"], "waiting_for_controller")
            self.assertNotIn("controller", facade.snapshot().health.degraded)
            self.assertEqual(facade.snapshot().last_error.code.value, "controller.unavailable")

    def test_rumble_mapping_change_does_not_restart_audio_but_filter_change_does(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = CoreFacade(
                config_repository=self.make_repo(Path(temp)),
                controller_factory=FakeControllerFactory(),
                mouse_output=FakeMouse(),
            )
            facade._reload_audio.clear()
            facade.update_config({"rumble": {"gate": 0.08}}, persist=False)
            self.assertFalse(facade._reload_audio.is_set())

            facade.update_config({"rumble": {"heavy_cutoff_hz": 180}}, persist=False)
            self.assertTrue(facade._reload_audio.is_set())

    def test_valid_persisted_config_clears_config_degraded_health(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "config.json").write_text("{broken", encoding="utf-8")
            facade = CoreFacade(
                config_repository=self.make_repo(root),
                controller_factory=FakeControllerFactory(),
                mouse_output=FakeMouse(),
            )
            self.assertIn("config", facade.snapshot().health.degraded)
            self.assertIsNotNone(facade.snapshot().last_error)

            facade.update_config({"theme": "Dark"})

            self.assertNotIn("config", facade.snapshot().health.degraded)
            self.assertIsNone(facade.snapshot().last_error)

    def test_mic_toggle_feedback_preserves_upstream_right_motor(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = CoreFacade(
                config_repository=self.make_repo(Path(temp)),
                controller_factory=FakeControllerFactory(),
                mouse_output=FakeMouse(),
            )
            pulses = []
            facade.controller.pulse = lambda left, right, duration: pulses.append((left, right, duration)) or True

            facade.toggle("trackpad")

            self.assertEqual(pulses, [(0, 140, 0.12)])


if __name__ == "__main__":
    unittest.main()
