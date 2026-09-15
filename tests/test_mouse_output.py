import ctypes
import unittest
from unittest.mock import patch

from dualsense_companion.domain.errors import DS5ForgeError
from dualsense_companion.platform.windows.mouse_output import WindowsMouseOutput


class FakeUser32:
    def __init__(self):
        self.results = []
        self.calls = 0

    def SendInput(self, _count, _input, _size):
        self.calls += 1
        if self.results:
            return self.results.pop(0)
        return 1


class Loader:
    def __init__(self, user32):
        self.user32 = user32


class MouseOutputTests(unittest.TestCase):
    def test_release_all_attempts_every_held_button_even_after_failure(self):
        user32 = FakeUser32()
        output = WindowsMouseOutput()
        with patch.object(ctypes, "windll", Loader(user32), create=True):
            output.button(True, True)
            output.button(False, True)
            self.assertTrue(output._left_down)
            self.assertTrue(output._right_down)

            user32.results = [0, 1]
            with self.assertRaises(DS5ForgeError):
                output.release_all()

            self.assertTrue(output._left_down)
            self.assertFalse(output._right_down)
            self.assertEqual(user32.calls, 4)

            output.release_all()
            self.assertFalse(output._left_down)
            self.assertFalse(output._right_down)

    def test_failed_button_send_does_not_mark_button_held(self):
        user32 = FakeUser32()
        user32.results = [0]
        output = WindowsMouseOutput()
        with patch.object(ctypes, "windll", Loader(user32), create=True):
            with self.assertRaises(DS5ForgeError):
                output.button(True, True)
        self.assertFalse(output._left_down)

    def test_named_mouse4_is_tracked_and_released(self):
        user32 = FakeUser32()
        output = WindowsMouseOutput()
        with patch.object(ctypes, "windll", Loader(user32), create=True):
            output.button_code("Mouse4", True)
            self.assertIn("mouse4", output._extra_down)
            output.release_all()
        self.assertNotIn("mouse4", output._extra_down)
        self.assertEqual(user32.calls, 2)

    def test_shared_touchpad_and_remap_owner_do_not_release_each_other(self):
        user32 = FakeUser32()
        output = WindowsMouseOutput()
        with patch.object(ctypes, "windll", Loader(user32), create=True):
            # Touchpad/L3 uses the legacy boolean surface while P3 remapping
            # uses the named-button surface. They intentionally share the
            # same physical ownership counter.
            output.button(True, True)
            output.button_code("left", True)
            self.assertEqual(output._button_refcounts["left"], 2)
            self.assertEqual(user32.calls, 1)

            output.button(True, False)
            self.assertTrue(output._left_down)
            self.assertEqual(output._button_refcounts["left"], 1)
            self.assertEqual(user32.calls, 1)

            output.button_code("left", False)
            self.assertFalse(output._left_down)
            self.assertNotIn("left", output._button_refcounts)
            self.assertEqual(user32.calls, 2)


if __name__ == "__main__":
    unittest.main()
