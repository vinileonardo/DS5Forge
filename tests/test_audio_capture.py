import sys
import types
import unittest
from unittest.mock import patch

from dualsense_companion.platform.windows.audio_capture import (
    WasapiLoopbackCapture,
    WasapiProcessLoopbackFactory,
)


class FakeStream:
    def __init__(self):
        self.stopped = False
        self.closed = False

    def read(self, frames, exception_on_overflow=False):
        return b"\x00" * (frames * 4)

    def stop_stream(self):
        self.stopped = True

    def close(self):
        self.closed = True


class FakePyAudio:
    def __init__(self):
        self.default_index = 1
        self.stream = FakeStream()
        self.terminated = False

    def get_host_api_info_by_type(self, api_type):
        if api_type != 13:
            raise AssertionError(f"unexpected WASAPI type: {api_type}")
        return {"defaultOutputDevice": self.default_index}

    def get_device_info_by_index(self, index):
        return {
            "index": index,
            "name": "Speakers",
            "isLoopbackDevice": False,
            "defaultSampleRate": 48_000,
            "maxInputChannels": 2,
        }

    def get_loopback_device_info_generator(self):
        yield {
            "index": 7,
            "name": "Speakers [Loopback]",
            "isLoopbackDevice": True,
            "defaultSampleRate": 48_000,
            "maxInputChannels": 2,
        }

    def open(self, **_kwargs):
        return self.stream

    def terminate(self):
        self.terminated = True


class AudioCaptureTests(unittest.TestCase):
    def test_default_device_change_uses_module_wasapi_constant(self):
        module = types.ModuleType("pyaudiowpatch")
        module.paWASAPI = 13
        module.paFloat32 = 1
        module.PyAudio = FakePyAudio

        with patch.dict(sys.modules, {"pyaudiowpatch": module}):
            capture = WasapiLoopbackCapture()
            with capture:
                self.assertEqual(capture.name, "Speakers [Loopback]")
                self.assertEqual(capture.sample_rate, 48_000)
                self.assertEqual(capture.channels, 2)
                self.assertFalse(capture.default_output_changed())
                capture._pyaudio.default_index = 2
                self.assertTrue(capture.default_output_changed())

        self.assertIsNone(capture._pyaudio)
        self.assertIsNone(capture._wasapi_type)

    def test_process_loopback_targets_one_pid_and_invalidates_on_game_change(self):
        class FakeProcessLoopback:
            instances = []

            def __init__(self, pid):
                self.pid = pid
                self.started = False
                self.stopped = False
                self.read_calls = 0
                self.__class__.instances.append(self)

            def start(self):
                self.started = True

            def get_format(self):
                return {
                    "sample_rate": 48_000,
                    "channels": 2,
                    "bits_per_sample": 32,
                    "block_align": 8,
                }

            def read(self):
                self.read_calls += 1
                return b"\x00" * 32

            def stop(self):
                self.stopped = True

        factory = WasapiProcessLoopbackFactory()
        self.assertFalse(factory.is_ready())
        self.assertTrue(
            factory.select_process(
                101,
                app_name="Black Myth: Wukong",
                executable_name="b1-Win64-Shipping.exe",
            )
        )
        self.assertTrue(factory.is_ready())

        with patch(
            "dualsense_companion.platform.windows.audio_capture._load_process_loopback_class",
            return_value=FakeProcessLoopback,
        ):
            capture = factory.open()
            with capture:
                self.assertEqual(capture.sample_rate, 48_000)
                self.assertEqual(capture.channels, 2)
                self.assertIn("Black Myth: Wukong", capture.name)
                self.assertIn("PID 101", capture.name)
                self.assertEqual(capture.read(), b"\x00" * 32)
                self.assertFalse(capture.default_output_changed())

                self.assertTrue(
                    factory.select_process(
                        202,
                        app_name="Kingdom Come: Deliverance II",
                        executable_name="KingdomCome.exe",
                    )
                )
                self.assertTrue(capture.default_output_changed())

        instance = FakeProcessLoopback.instances[0]
        self.assertTrue(instance.started)
        self.assertEqual(instance.pid, 101)
        self.assertEqual(instance.read_calls, 1)
        self.assertTrue(instance.stopped)
        self.assertTrue(factory.clear_process())
        self.assertFalse(factory.is_ready())


if __name__ == "__main__":
    unittest.main()
