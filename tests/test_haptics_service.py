import struct
import threading
import unittest

from dualsense_companion.core.config import default_config
from dualsense_companion.core.haptics_service import HapticsService


class HapticsServiceTests(unittest.TestCase):
    def test_run_once_processes_audio_and_neutralizes_on_device_change(self):
        outputs = []
        audio = []

        class Capture:
            sample_rate = 48_000
            channels = 1
            frames = 64
            name = "Fake Loopback"

            def __init__(self):
                self.reads = 0

            def read(self):
                self.reads += 1
                return struct.pack("<" + "f" * self.frames, *([0.9] * self.frames))

            def default_output_changed(self):
                return self.reads > 0

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

        times = iter((0.0, 1.0, 2.1))
        service = HapticsService(
            lambda left, right: outputs.append((left, right)) or True,
            lambda: default_config()["rumble"],
            lambda: True,
            capture_factory=Factory(),
            on_audio=lambda status, device, error: audio.append((status, device, error)),
            clock=lambda: next(times),
        )
        service._run_once()

        self.assertEqual(capture.reads, 1)
        self.assertEqual(audio[0], ("listening", "Fake Loopback", None))
        self.assertTrue(any(left > 0 or right > 0 for left, right in outputs))
        self.assertEqual(outputs[-1], (0, 0))

    def test_mapping_config_is_refreshed_without_rebuilding_capture(self):
        configs = []
        base = default_config()["rumble"]

        class Capture:
            sample_rate = 48_000
            channels = 1
            frames = 4
            name = "Fake Loopback"

            def __init__(self):
                self.reads = 0

            def read(self):
                self.reads += 1
                return struct.pack("<ffff", 0.9, 0.9, 0.9, 0.9)

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

        def config_provider():
            configs.append(True)
            return dict(base)

        times = iter((0.0, 1.0, 2.1))
        service = HapticsService(
            lambda _left, _right: True,
            config_provider,
            lambda: True,
            capture_factory=Factory(),
            clock=lambda: next(times),
        )
        service._run_once()

        self.assertGreaterEqual(len(configs), 2)
        self.assertEqual(capture.reads, 1)

    def test_stop_closes_active_capture_to_interrupt_blocked_read(self):
        read_entered = threading.Event()
        release_read = threading.Event()
        errors = []

        class Capture:
            sample_rate = 48_000
            channels = 1
            frames = 64
            name = "Blocking Loopback"

            def __init__(self):
                self.close_calls = 0

            def read(self):
                read_entered.set()
                release_read.wait(5.0)
                raise RuntimeError("capture closed")

            def default_output_changed(self):
                return False

            def close(self):
                self.close_calls += 1
                release_read.set()

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
            lambda _left, _right: True,
            lambda: default_config()["rumble"],
            lambda: True,
            capture_factory=Factory(),
            on_error=errors.append,
        )
        service.start()
        self.assertTrue(read_entered.wait(1.0))

        service.stop(join_timeout=1.0)

        self.assertFalse(service.is_alive())
        self.assertGreaterEqual(capture.close_calls, 1)
        self.assertEqual(errors, [])

    def test_missing_capture_adapter_reports_audio_error(self):
        errors = []
        audio = []
        service = HapticsService(
            lambda _left, _right: True,
            lambda: default_config()["rumble"],
            lambda: True,
            capture_factory=None,
            on_error=errors.append,
            on_audio=lambda status, device, error: audio.append((status, device, error)),
        )

        service.run()

        self.assertEqual(errors[0].code.value, "audio.unavailable")
        self.assertEqual(audio, [("error", None, "No audio capture adapter is configured.")])

    def test_failed_motor_write_is_not_deduplicated_as_success(self):
        calls = []
        errors = []

        def output(left, right):
            calls.append((left, right))
            return len(calls) > 1

        service = HapticsService(
            output,
            lambda: {},
            lambda: True,
            on_error=errors.append,
        )
        service._set_motors(100, 50)
        self.assertEqual(service.last_left, -1)
        self.assertEqual(service.last_right, -1)
        service._set_motors(100, 50)

        self.assertEqual(calls, [(100, 50), (100, 50)])
        self.assertEqual((service.last_left, service.last_right), (100, 50))
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].code.value, "controller.output_failed")


if __name__ == "__main__":
    unittest.main()
