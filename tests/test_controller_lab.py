import time
import unittest

from dualsense_companion.core.controller_lab import HapticsTestBench, TriggerPreviewCoordinator
from dualsense_companion.core.telemetry import BoundedLatestQueue, TelemetryPublisher
from dualsense_companion.domain.errors import DS5ForgeError, ErrorCode
from dualsense_companion.domain.models import ControllerInput, TriggerState


class ControllerLabCoordinatorTests(unittest.TestCase):
    def wait_for(self, predicate, timeout=1.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.005)
        return predicate()

    def test_trigger_preview_times_out_and_neutralizes(self):
        applied = []
        resets = []
        states = []
        coordinator = TriggerPreviewCoordinator(
            lambda state: applied.append(state),
            lambda: resets.append(True),
            on_state=states.append,
        )

        preview = coordinator.start(TriggerState(), duration_ms=20)

        self.assertEqual(preview.status, "running")
        self.assertTrue(
            self.wait_for(lambda: coordinator.state is not None and coordinator.state.status == "timed_out")
        )
        self.assertEqual(len(applied), 1)
        self.assertGreaterEqual(len(resets), 1)
        self.assertEqual(states[-1].status, "timed_out")

    def test_trigger_preview_is_single_flight_and_cancel_is_typed(self):
        resets = []
        coordinator = TriggerPreviewCoordinator(lambda _state: None, lambda: resets.append(True))
        coordinator.start(TriggerState(), duration_ms=500)
        with self.assertRaises(DS5ForgeError) as raised:
            coordinator.start(TriggerState(), duration_ms=500)
        self.assertEqual(raised.exception.code, ErrorCode.TRIGGER_PREVIEW_BUSY)
        cancelled = coordinator.cancel()
        self.assertIsNotNone(cancelled)
        self.assertEqual(cancelled.status, "cancelled")
        self.assertGreaterEqual(len(resets), 1)

    def test_trigger_preview_reset_failure_is_not_silent(self):
        coordinator = TriggerPreviewCoordinator(lambda _state: None, lambda: (_ for _ in ()).throw(RuntimeError("USB")))
        coordinator.start(TriggerState(), duration_ms=500)
        with self.assertRaises(DS5ForgeError) as raised:
            coordinator.cancel()
        self.assertEqual(raised.exception.code, ErrorCode.TRIGGER_OUTPUT_FAILED)
        self.assertEqual(coordinator.state.status, "error")

    def test_haptics_test_is_bounded_and_neutralized(self):
        output = []
        neutralized = []
        states = []
        bench = HapticsTestBench(
            lambda left, right: output.append((left, right)),
            lambda: neutralized.append(True),
            on_state=states.append,
        )

        run = bench.start(left=100, right=80, duration_ms=20)

        self.assertEqual(run.status, "running")
        self.assertTrue(self.wait_for(lambda: bench.run is not None and bench.run.status == "completed"))
        self.assertEqual(output, [(100, 80)])
        self.assertGreaterEqual(len(neutralized), 1)
        self.assertEqual(states[-1].status, "completed")

    def test_haptics_test_lock_and_cancel(self):
        neutralized = []
        bench = HapticsTestBench(lambda _left, _right: None, lambda: neutralized.append(True))
        bench.start(duration_ms=500)
        with self.assertRaises(DS5ForgeError) as raised:
            bench.start(duration_ms=500)
        self.assertEqual(raised.exception.code, ErrorCode.HAPTICS_TEST_BUSY)
        cancelled = bench.cancel()
        self.assertIsNotNone(cancelled)
        self.assertEqual(cancelled.status, "cancelled")
        self.assertGreaterEqual(len(neutralized), 1)

    def test_haptics_test_neutralization_failure_is_structured(self):
        bench = HapticsTestBench(lambda _left, _right: None, lambda: (_ for _ in ()).throw(RuntimeError("USB")))
        bench.start(duration_ms=500)
        with self.assertRaises(DS5ForgeError) as raised:
            bench.cancel()
        self.assertEqual(raised.exception.code, ErrorCode.HAPTICS_TEST_FAILED)
        self.assertEqual(bench.run.status, "error")


class TelemetryTransportTests(unittest.TestCase):
    def test_decimator_is_latest_value_and_max_thirty_hz(self):
        now = [0.0]
        published = []
        publisher = TelemetryPublisher(max_hz=30, clock=lambda: now[0], on_publish=published.append)
        first = publisher.offer(ControllerInput(cross=True))
        now[0] = 0.01
        self.assertIsNone(publisher.offer(ControllerInput(square=True)))
        now[0] = 0.04
        second = publisher.offer(ControllerInput(triangle=True))

        self.assertEqual([item.sequence for item in published], [1, 2])
        self.assertEqual(first.input.cross, True)
        self.assertEqual(second.input.triangle, True)
        self.assertEqual(publisher.latest.triangle, True)
        self.assertEqual(second.sample_rate_hz, 30)

    def test_bounded_latest_queue_drops_old_history(self):
        queue = BoundedLatestQueue[int](maxsize=2)
        for value in (1, 2, 3):
            queue.put_latest(value)
        self.assertLessEqual(queue.qsize(), 2)
        self.assertEqual(queue.get_nowait(), 2)
        self.assertEqual(queue.get_nowait(), 3)


if __name__ == "__main__":
    unittest.main()
