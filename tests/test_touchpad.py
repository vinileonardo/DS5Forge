import unittest

from dualsense_companion.core.config import default_config
from dualsense_companion.core.touchpad import GestureInterpreter, TouchpadService
from dualsense_companion.domain.models import ControllerInput, TouchPoint


class FakeMouse:
    def __init__(self):
        self.actions = []

    def move(self, dx, dy):
        self.actions.append(("move", dx, dy))

    def button(self, left, down):
        self.actions.append(("button", left, down))

    def wheel(self, amount, horizontal=False):
        self.actions.append(("wheel", amount, horizontal))

    def release_all(self):
        self.actions.append(("release_all",))


class TouchpadTests(unittest.TestCase):
    def setUp(self):
        self.config = default_config()["trackpad"]

    def test_one_finger_tap_and_move(self):
        interpreter = GestureInterpreter()
        interpreter.process(ControllerInput(touch0=TouchPoint(True, 100, 100)), self.config, now=0.0)
        moved = interpreter.process(ControllerInput(touch0=TouchPoint(True, 120, 100)), self.config, now=0.02)
        released = interpreter.process(ControllerInput(), self.config, now=0.1)
        self.assertTrue(any(action.kind == "move" for action in moved.actions))
        self.assertEqual(
            [(action.left, action.down) for action in released.actions if action.kind == "button"],
            [(True, True), (True, False)],
        )

    def test_two_finger_tap_is_right_click_and_scroll_is_semantic(self):
        interpreter = GestureInterpreter()
        interpreter.process(
            ControllerInput(touch0=TouchPoint(True, 100, 100), touch1=TouchPoint(True, 200, 100)),
            self.config,
            now=0.0,
        )
        released = interpreter.process(ControllerInput(), self.config, now=0.1)
        self.assertEqual(
            [(action.left, action.down) for action in released.actions if action.kind == "button"],
            [(False, True), (False, False)],
        )

        interpreter = GestureInterpreter()
        interpreter.process(
            ControllerInput(touch0=TouchPoint(True, 100, 100), touch1=TouchPoint(True, 200, 100)),
            self.config,
            now=0.0,
        )
        scroll = interpreter.process(
            ControllerInput(touch0=TouchPoint(True, 100, 250), touch1=TouchPoint(True, 200, 250)),
            self.config,
            now=0.02,
        )
        self.assertTrue(any(action.kind == "wheel" for action in scroll.actions))

    def test_reset_releases_held_buttons(self):
        interpreter = GestureInterpreter()
        interpreter.process(ControllerInput(l3=True), self.config, now=0.0)
        actions = interpreter.reset_state()
        self.assertIn(("button", True, False), [(a.kind, a.left, a.down) for a in actions])

    def test_service_reset_calls_output_release(self):
        output = FakeMouse()
        service = TouchpadService(output, lambda: self.config)
        service.reset()
        self.assertIn(("release_all",), output.actions)

    def test_mic_toggle_target_and_edge_are_preserved_when_disabling(self):
        output = FakeMouse()
        targets = []
        config = {"trackpad": self.config, "mic_button": "trackpad"}
        service = TouchpadService(output, lambda: config, toggle_callback=targets.append)
        service.handle(ControllerInput(mic_button=True))
        service.set_enabled(False)
        service.handle(ControllerInput(mic_button=True))
        self.assertEqual(targets, ["trackpad"])

    def test_disable_failure_retries_release_all(self):
        class FailingDisableMouse(FakeMouse):
            def __init__(self):
                super().__init__()
                self.held = False
                self.release_calls = 0

            def button(self, left, down):
                if down:
                    self.held = True
                    return
                if self.held:
                    raise RuntimeError("synthetic release failed once")

            def release_all(self):
                self.release_calls += 1
                self.held = False

        output = FailingDisableMouse()
        errors = []
        service = TouchpadService(output, lambda: self.config, error_callback=errors.append)
        service.handle(ControllerInput(l3=True))
        service.set_enabled(False)

        self.assertFalse(output.held)
        self.assertEqual(output.release_calls, 1)
        self.assertTrue(errors)

    def test_output_failure_releases_synthetic_buttons_and_resets_interpreter(self):
        class FailingMouse(FakeMouse):
            def __init__(self):
                super().__init__()
                self.held = False
                self.release_calls = 0

            def button(self, left, down):
                self.actions.append(("button", left, down))
                if down:
                    self.held = True
                    return
                if self.held:
                    raise RuntimeError("synthetic release failed once")

            def release_all(self):
                self.release_calls += 1
                self.held = False

        output = FailingMouse()
        errors = []
        service = TouchpadService(output, lambda: self.config, error_callback=errors.append)
        service.handle(ControllerInput(touch0=TouchPoint(True, 100, 100)))
        service.handle(ControllerInput())

        self.assertFalse(output.held)
        self.assertEqual(output.release_calls, 1)
        self.assertFalse(service.interpreter.prev_active0)
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
