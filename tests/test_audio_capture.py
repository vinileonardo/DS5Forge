import sys
import types
import unittest
from unittest.mock import patch

from dualsense_companion.platform.windows.audio_capture import WasapiLoopbackCapture


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


if __name__ == "__main__":
    unittest.main()
