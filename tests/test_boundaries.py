import re
import unittest
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[1] / "source" / "dualsense_companion"
WINDOWS_ROOT = SOURCE_ROOT / "platform" / "windows"


class BoundaryAuditTests(unittest.TestCase):
    def test_windows_hardware_apis_stay_inside_platform_boundary(self):
        forbidden = re.compile(r"(?:from\s+pydualsense|import\s+pydualsense|pyaudiowpatch|ctypes\.windll|SendInput\()")
        for path in SOURCE_ROOT.rglob("*.py"):
            if WINDOWS_ROOT in path.parents:
                continue
            self.assertIsNone(forbidden.search(path.read_text(encoding="utf-8")), path)

    def test_core_does_not_import_platform_implementations(self):
        core_root = SOURCE_ROOT / "core"
        forbidden = re.compile(r"(?:from|import)\s+\.{0,2}platform(?:\.|\s)|dualsense_companion\.platform")
        for path in core_root.rglob("*.py"):
            self.assertIsNone(forbidden.search(path.read_text(encoding="utf-8")), path)

    def test_no_wireless_implementation_or_silent_operational_pass(self):
        for path in SOURCE_ROOT.rglob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            self.assertNotRegex(text, r"(?:import|from).*bluetooth|(?:import|from).*wireless")
            self.assertNotRegex(text, r"except\s+(?:exception|baseexception).*:\s*pass")


if __name__ == "__main__":
    unittest.main()
