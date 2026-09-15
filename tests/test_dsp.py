import unittest

from dualsense_companion.core.config import default_config
from dualsense_companion.core.dsp import Biquad, EnvelopeFollower, map_rumble_level


class DspTests(unittest.TestCase):
    def test_gate_and_impact_mapping_match_contract(self):
        config = default_config()["rumble"]
        self.assertEqual(map_rumble_level(0.0, 0.0, config), 0)
        self.assertGreater(map_rumble_level(config["impact_level"], 0.0, config), 0)
        self.assertLessEqual(map_rumble_level(10.0, 10.0, config), 255)

    def test_envelope_attack_and_release_are_bounded(self):
        follower = EnvelopeFollower(5, 100, 10)
        rising = follower.update(1.0)
        falling = follower.update(0.0)
        self.assertGreater(rising, falling)
        self.assertGreaterEqual(falling, 0.0)

    def test_biquad_keeps_state_across_chunks(self):
        filter_ = Biquad.lowpass(48_000, 150)
        first = filter_.process([1.0] + [0.0] * 9)
        second = filter_.process([0.0] * 10)
        self.assertEqual(len(first), 10)
        self.assertEqual(len(second), 10)
        self.assertTrue(all(abs(value) < 10 for value in first + second))


if __name__ == "__main__":
    unittest.main()
