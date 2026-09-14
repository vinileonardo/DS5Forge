import time
import unittest

from dualsense_companion.core.controller_service import ControllerService
from dualsense_companion.domain.models import (
    BatterySnapshot,
    ControllerCapabilities,
    ControllerIdentity,
    ControllerReading,
)


class FakeAdapter:
    identity = ControllerIdentity(model="Fake DualSense")
    capabilities = ControllerCapabilities()

    def __init__(self):
        self.connected = True
        self.motors = []
        self.closed = False
        self.neutralized = False

    def is_connected(self):
        return self.connected

    def read(self):
        return ControllerReading(connected=self.connected, battery=BatterySnapshot(level=77))

    def set_motors(self, left, right):
        self.motors.append((left, right))

    def neutralize(self):
        self.neutralized = True
        self.set_motors(0, 0)

    def startup_feedback(self):
        return None

    def close(self):
        self.closed = True


class FakeFactory:
    def __init__(self):
        self.adapters = [FakeAdapter(), FakeAdapter()]
        self.calls = 0

    def connect(self):
        adapter = self.adapters[min(self.calls, len(self.adapters) - 1)]
        self.calls += 1
        return adapter


class LifecycleTests(unittest.TestCase):
    def test_default_polling_preserves_high_frequency_touch_input(self):
        service = ControllerService(FakeFactory())
        self.assertLessEqual(service.poll_interval, 1.0 / 200.0)

    def wait_for(self, predicate, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.01)
        return predicate()

    def test_startup_feedback_runs_before_connected_services(self):
        factory = FakeFactory()
        order = []
        factory.adapters[0].startup_feedback = lambda: order.append("feedback")
        service = ControllerService(
            factory,
            on_connected=lambda _adapter: order.append("connected-services"),
            poll_interval=0.01,
            min_backoff=0.01,
            max_backoff=0.02,
        )
        service.start()
        self.assertTrue(self.wait_for(lambda: len(order) >= 2))
        service.stop()
        self.assertEqual(order[:2], ["feedback", "connected-services"])

    def test_connected_callback_failure_runs_disconnect_cleanup(self):
        factory = FakeFactory()
        cleanup_calls = []
        service = ControllerService(
            factory,
            on_connected=lambda _adapter: (_ for _ in ()).throw(RuntimeError("boom")),
            on_disconnected=lambda: cleanup_calls.append(True),
            poll_interval=0.01,
            min_backoff=0.01,
            max_backoff=0.02,
        )
        service.start()
        self.assertTrue(self.wait_for(lambda: bool(cleanup_calls)))
        service.stop()
        self.assertTrue(cleanup_calls)
        self.assertTrue(factory.adapters[0].neutralized)
        self.assertTrue(factory.adapters[0].closed)

    def test_connect_reconnect_and_shutdown_neutralize(self):
        factory = FakeFactory()
        states = []
        service = ControllerService(
            factory,
            on_lifecycle=lambda note: states.append(note.state.value),
            poll_interval=0.01,
            min_backoff=0.01,
            max_backoff=0.02,
        )
        service.start()
        self.assertTrue(self.wait_for(lambda: factory.calls >= 1 and service.adapter is factory.adapters[0]))
        factory.adapters[0].connected = False
        self.assertTrue(self.wait_for(lambda: factory.calls >= 2 and service.adapter is factory.adapters[1]))
        service.stop()
        self.assertFalse(service.alive)
        self.assertTrue(factory.adapters[0].neutralized)
        self.assertTrue(factory.adapters[0].closed)
        self.assertTrue(factory.adapters[1].neutralized)
        self.assertTrue(factory.adapters[1].closed)
        self.assertIn("reconnecting", states)
        self.assertIn("stopping", states)


if __name__ == "__main__":
    unittest.main()
