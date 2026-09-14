import sys
import types
import unittest
from enum import IntFlag
from unittest.mock import patch

from dualsense_companion.domain.errors import ControllerUnavailableError
from dualsense_companion.platform.windows.dualsense_adapter import PyDualSenseFactory


class ConnectionType(IntFlag):
    BT = 0
    USB = 1
    ERROR = 255


class FakeRaw:
    def __init__(self, connection_type):
        self.conType = connection_type
        self.closed = False

    def init(self):
        return None

    def close(self):
        self.closed = True


class WindowsAdapterTests(unittest.TestCase):
    def test_factory_rejects_non_usb_controller_after_library_detection(self):
        raw = FakeRaw(ConnectionType.BT)
        package = types.ModuleType("pydualsense")
        package.pydualsense = lambda: raw
        enums = types.ModuleType("pydualsense.enums")
        enums.ConnectionType = ConnectionType

        with patch.dict(sys.modules, {"pydualsense": package, "pydualsense.enums": enums}):
            with self.assertRaises(ControllerUnavailableError) as ctx:
                PyDualSenseFactory().connect()

        self.assertTrue(raw.closed)
        self.assertIn("USB only", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
