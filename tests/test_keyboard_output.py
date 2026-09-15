import unittest
from unittest.mock import patch

from dualsense_companion.platform.windows.keyboard_output import WindowsKeyboardOutput


class KeyboardOutputTests(unittest.TestCase):
    def test_overlapping_combinations_reference_count_shared_modifier(self):
        output = WindowsKeyboardOutput()
        calls: list[tuple[int, bool]] = []

        with patch.object(output, "_send", side_effect=lambda vk, down: calls.append((vk, down))):
            output.key("Ctrl+A", True)
            output.key("CTRL+B", True)
            output.key("CTRL+A", False)

            self.assertEqual(output._key_refcounts["CTRL"], 1)
            self.assertNotIn("A", output._key_refcounts)
            self.assertIn("B", output._key_refcounts)
            self.assertEqual(calls, [(0x11, True), (ord("A"), True), (ord("B"), True), (ord("A"), False)])

            output.key("CTRL+B", False)

        self.assertEqual(calls[-2:], [(ord("B"), False), (0x11, False)])
        self.assertEqual(output._key_refcounts, {})
        self.assertEqual(output._held_outputs, {})

    def test_partial_release_failure_keeps_only_unreleased_ownership_for_retry(self):
        output = WindowsKeyboardOutput()
        failed_once = False
        calls: list[tuple[int, bool]] = []

        def send(vk: int, down: bool) -> None:
            nonlocal failed_once
            calls.append((vk, down))
            if vk == ord("A") and not down and not failed_once:
                failed_once = True
                raise RuntimeError("synthetic key-up failed")

        with patch.object(output, "_send", side_effect=send):
            output.key("CTRL+A", True)
            output.key("CTRL+B", True)
            with self.assertRaises(RuntimeError):
                output.key("CTRL+A", False)

            self.assertEqual(output._held_outputs["CTRL+A"], ("A",))
            self.assertEqual(output._key_refcounts["CTRL"], 1)
            self.assertEqual(output._key_refcounts["A"], 1)

            output.release_all()

        self.assertEqual(output._key_refcounts, {})
        self.assertEqual(output._held_outputs, {})
        self.assertGreaterEqual(calls.count((ord("A"), False)), 2)


if __name__ == "__main__":
    unittest.main()
