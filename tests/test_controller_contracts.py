import unittest
from types import SimpleNamespace

from dualsense_companion.domain.errors import CapabilityUnavailableError, DS5ForgeError, ErrorCode
from dualsense_companion.domain.models import (
    AdaptiveTriggerEffect,
    TriggerState,
    normalize_controller_input,
)
from dualsense_companion.platform.windows.dualsense_adapter import PyDualSenseAdapter


class FakeTrigger:
    def __init__(self):
        self.mode = None
        self.forces = []

    def setMode(self, mode):
        self.mode = mode

    def setForce(self, force_id, force):
        while len(self.forces) <= force_id:
            self.forces.append(None)
        self.forces[force_id] = force


class TriggerModes:
    Off = "off"
    Rigid = "rigid"
    Pulse_AB = "pulse_ab"


class ControllerContractTests(unittest.TestCase):
    def test_normalization_handles_complete_raw_input_and_optional_fields(self):
        raw = SimpleNamespace(
            square=True,
            DpadUp=True,
            L1=True,
            R2Btn=True,
            LX=-127,
            LY=0,
            RX=127,
            RY=64,
            L2_value=128,
            R2_value=255,
            trackPadTouch0=SimpleNamespace(isActive=True, X=960, Y=540),
            trackPadTouch1=SimpleNamespace(isActive=False, X=0, Y=0),
        )

        value = normalize_controller_input(raw)

        self.assertTrue(value.square)
        self.assertTrue(value.dpad_up)
        self.assertTrue(value.l1)
        self.assertTrue(value.r2_button)
        self.assertAlmostEqual(value.sticks.left_x, -1.0)
        self.assertAlmostEqual(value.sticks.left_y, 0.0)
        self.assertAlmostEqual(value.sticks.right_x, 1.0)
        self.assertAlmostEqual(value.sticks.right_y, 64 / 127)
        self.assertAlmostEqual(value.l2, 128 / 255)
        self.assertEqual((value.touch0.active, value.touch0.x, value.touch0.y), (True, 960.0, 540.0))
        self.assertFalse(value.touch1.active)

    def test_normalization_accepts_nested_normalized_sticks_and_defaults(self):
        value = normalize_controller_input({"sticks": {"left_x": 0.5, "right_y": -0.5}, "l2": 0.25})

        self.assertEqual(value.sticks.left_x, 0.5)
        self.assertEqual(value.sticks.right_y, -0.5)
        self.assertEqual(value.l2, 0.25)
        self.assertEqual(value.r2, 0.0)
        self.assertFalse(value.touch0.active)

    def test_adapter_detects_surface_capabilities_and_maps_outputs(self):
        left = FakeTrigger()
        right = FakeTrigger()
        raw = SimpleNamespace(
            connected=True,
            state=SimpleNamespace(trackPadTouch0=object(), trackPadTouch1=object(), micBtn=False),
            light=SimpleNamespace(setColorI=lambda *_args: None, TouchpadColor=(0, 0, 0)),
            triggerL=left,
            triggerR=right,
            setLeftMotor=lambda _value: None,
            setRightMotor=lambda _value: None,
            battery=SimpleNamespace(Level=50, Charging=False),
            close=lambda: None,
        )
        adapter = PyDualSenseAdapter(raw, trigger_modes=TriggerModes)

        self.assertTrue(adapter.capabilities.lightbar)
        self.assertTrue(adapter.capabilities.adaptive_triggers)
        self.assertTrue(adapter.capabilities.touchpad)
        adapter.set_triggers(
            TriggerState(
                left=AdaptiveTriggerEffect(mode="pulse", start_position=10, end_position=200, force=80),
            )
        )
        self.assertEqual(left.mode, TriggerModes.Pulse_AB)
        self.assertEqual(left.forces[:3], [10, 80, 200])
        adapter.reset_triggers()
        self.assertEqual(left.mode, TriggerModes.Off)
        self.assertEqual(left.forces, [0, 0, 0, 0, 0, 0, 0])

    def test_unsupported_lightbar_never_calls_hardware(self):
        raw = SimpleNamespace(
            connected=True,
            state=SimpleNamespace(),
            light=SimpleNamespace(),
            triggerL=None,
            triggerR=None,
            setLeftMotor=lambda _value: None,
            setRightMotor=lambda _value: None,
            battery=SimpleNamespace(Level=0, Charging=None),
            close=lambda: None,
        )
        adapter = PyDualSenseAdapter(raw)

        with self.assertRaises(CapabilityUnavailableError):
            adapter.set_lightbar(adapter.get_lightbar())

    def test_adapter_output_failures_are_structured(self):
        class BrokenTrigger(FakeTrigger):
            def setMode(self, _mode):
                raise RuntimeError("write failed")

        left = BrokenTrigger()
        right = BrokenTrigger()
        raw = SimpleNamespace(
            connected=True,
            state=SimpleNamespace(),
            light=SimpleNamespace(setColorI=lambda *_args: None),
            triggerL=left,
            triggerR=right,
            setLeftMotor=lambda _value: None,
            setRightMotor=lambda _value: None,
            battery=SimpleNamespace(Level=0, Charging=None),
            close=lambda: None,
        )
        adapter = PyDualSenseAdapter(raw, trigger_modes=TriggerModes)

        with self.assertRaises(DS5ForgeError) as raised:
            adapter.set_triggers(TriggerState())
        self.assertEqual(raised.exception.code, ErrorCode.TRIGGER_OUTPUT_FAILED)


if __name__ == "__main__":
    unittest.main()
