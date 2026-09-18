import sys
import types
import unittest
from enum import IntFlag
from unittest.mock import patch

from dualsense_companion.domain.errors import ControllerUnavailableError, DS5ForgeError
from dualsense_companion.platform.windows.dualsense_adapter import PyDualSenseAdapter, PyDualSenseFactory


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


class FakeHidInfo:
    def __init__(self, path: bytes, *, interface_number: int = 3, serial_number: str | None = None):
        self.path = path
        self.vendor_id = 0x054C
        self.product_id = 0x0CE6
        self.interface_number = interface_number
        self.serial_number = serial_number
        self.product_string = "DualSense Wireless Controller"


class FakeHidDevice:
    def __init__(self, info):
        self.info = info
        self.closed = False

    def close(self):
        self.closed = True


class StableRaw:
    instances = []

    def __init__(self):
        self.conType = None
        self.connected = True
        self.closed = False
        self.device = None
        StableRaw.instances.append(self)

    def init(self):
        self.device, _is_edge = self._pydualsense__find_device()
        self.conType = ConnectionType.USB

    def close(self):
        self.closed = True
        if self.device is not None and not self.device.closed:
            self.device.close()


class FakeThread:
    def __init__(self, alive: bool):
        self.alive = alive

    def is_alive(self):
        return self.alive


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds: float):
        self.value += seconds


class WindowsAdapterTests(unittest.TestCase):
    def setUp(self):
        StableRaw.instances = []

    def test_adapter_detects_dead_pydualsense_report_thread_even_if_connected_flag_is_stale(self):
        raw = types.SimpleNamespace(
            connected=True,
            ds_thread=True,
            report_thread=FakeThread(False),
            light=types.SimpleNamespace(setColorI=lambda *_args: None, playerNumber=None),
            triggerL=None,
            triggerR=None,
            state=types.SimpleNamespace(),
        )
        adapter = PyDualSenseAdapter(raw)
        self.assertFalse(adapter.is_connected())

    def test_adapter_accepts_live_pydualsense_report_thread(self):
        raw = types.SimpleNamespace(
            connected=True,
            ds_thread=True,
            report_thread=FakeThread(True),
            light=types.SimpleNamespace(setColorI=lambda *_args: None, playerNumber=None),
            triggerL=None,
            triggerR=None,
            state=types.SimpleNamespace(),
        )
        adapter = PyDualSenseAdapter(raw)
        self.assertTrue(adapter.is_connected())

    def test_adapter_detects_stalled_report_stream_even_when_thread_and_connected_flag_stay_alive(self):
        clock = FakeClock()
        first_report = object()
        raw = types.SimpleNamespace(
            connected=True,
            ds_thread=True,
            report_thread=FakeThread(True),
            states=first_report,
            light=types.SimpleNamespace(setColorI=lambda *_args: None, playerNumber=None),
            triggerL=None,
            triggerR=None,
            state=types.SimpleNamespace(),
        )
        adapter = PyDualSenseAdapter(raw, report_stale_after=2.0, monotonic=clock)
        self.assertTrue(adapter.is_connected())
        clock.advance(1.5)
        self.assertTrue(adapter.is_connected())
        clock.advance(0.6)
        self.assertFalse(adapter.is_connected())

    def test_adapter_resets_report_watchdog_when_new_report_arrives(self):
        clock = FakeClock()
        raw = types.SimpleNamespace(
            connected=True,
            ds_thread=True,
            report_thread=FakeThread(True),
            states=object(),
            light=types.SimpleNamespace(setColorI=lambda *_args: None, playerNumber=None),
            triggerL=None,
            triggerR=None,
            state=types.SimpleNamespace(),
        )
        adapter = PyDualSenseAdapter(raw, report_stale_after=2.0, monotonic=clock)
        clock.advance(1.8)
        raw.states = object()
        self.assertTrue(adapter.is_connected())
        clock.advance(1.8)
        self.assertTrue(adapter.is_connected())

    def test_adapter_exclusive_output_passthrough_suppresses_generated_writes_and_restores_them(self):
        writes = []
        normal_report = [0x02] + [0x11] * 63

        def write_report(report):
            writes.append(list(report))

        raw = types.SimpleNamespace(
            connected=True,
            ds_thread=True,
            report_thread=FakeThread(True),
            light=types.SimpleNamespace(setColorI=lambda *_args: None, playerNumber=None),
            triggerL=None,
            triggerR=None,
            state=types.SimpleNamespace(),
            writeReport=write_report,
            prepareReport=lambda: list(normal_report),
        )
        adapter = PyDualSenseAdapter(raw)
        self.assertTrue(adapter.exclusive_output_passthrough_available())

        adapter.begin_exclusive_output_passthrough()
        raw.writeReport(normal_report)
        self.assertEqual(writes, [])

        game_report = bytes([0x02] + [0x22] * 63)
        adapter.write_exclusive_output_report(game_report)
        self.assertEqual(writes, [list(game_report)])

        adapter.end_exclusive_output_passthrough()
        self.assertEqual(writes[-1], normal_report)
        raw.writeReport(game_report)
        self.assertEqual(writes[-1], list(game_report))

    def test_adapter_native_and_exclusive_output_passthrough_share_write_suppression_ownership(self):
        writes = []
        normal_report = [0x02] + [0x11] * 63

        def write_report(report):
            writes.append(list(report))

        raw = types.SimpleNamespace(
            connected=True,
            ds_thread=True,
            report_thread=FakeThread(True),
            light=types.SimpleNamespace(setColorI=lambda *_args: None, playerNumber=None),
            triggerL=None,
            triggerR=None,
            state=types.SimpleNamespace(),
            writeReport=write_report,
            prepareReport=lambda: list(normal_report),
        )
        adapter = PyDualSenseAdapter(raw)

        adapter.begin_native_game_output_passthrough()
        raw.writeReport(normal_report)
        self.assertEqual(writes, [])

        adapter.begin_exclusive_output_passthrough()
        game_report = bytes([0x02] + [0x22] * 63)
        adapter.write_exclusive_output_report(game_report)
        self.assertEqual(writes, [list(game_report)])

        adapter.end_exclusive_output_passthrough()
        raw.writeReport(normal_report)
        self.assertEqual(writes, [list(game_report)])

        adapter.end_native_game_output_passthrough()
        self.assertEqual(writes[-1], normal_report)
        raw.writeReport(game_report)
        self.assertEqual(writes[-1], list(game_report))

    def test_adapter_rejects_invalid_exclusive_output_report(self):
        raw = types.SimpleNamespace(
            connected=True,
            ds_thread=True,
            report_thread=FakeThread(True),
            light=types.SimpleNamespace(setColorI=lambda *_args: None, playerNumber=None),
            triggerL=None,
            triggerR=None,
            state=types.SimpleNamespace(),
            writeReport=lambda _report: None,
            prepareReport=lambda: [0x02] + [0] * 63,
        )
        adapter = PyDualSenseAdapter(raw)
        adapter.begin_exclusive_output_passthrough()
        with self.assertRaises(DS5ForgeError):
            adapter.write_exclusive_output_report(bytes([0x31] + [0] * 77))
        adapter.end_exclusive_output_passthrough()

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

    def test_factory_pins_one_concrete_hid_path_when_multiple_dualsense_are_present(self):
        first = FakeHidInfo(b"hid-path-a", serial_number="AA:BB:CC")
        second = FakeHidInfo(b"hid-path-b", serial_number="DD:EE:FF")
        devices = [second, first]
        opened = []

        package = types.ModuleType("pydualsense")
        package.pydualsense = StableRaw
        enums = types.ModuleType("pydualsense.enums")
        enums.ConnectionType = ConnectionType
        hidguardian = types.ModuleType("pydualsense.hidguardian")
        hidguardian.check_hide = lambda: False
        package.hidguardian = hidguardian
        hidapi = types.ModuleType("hidapi")
        hidapi.enumerate = lambda **_kwargs: list(devices)

        def open_device(*, info):
            opened.append(info.path)
            return FakeHidDevice(info)

        hidapi.Device = open_device
        modules = {
            "pydualsense": package,
            "pydualsense.enums": enums,
            "pydualsense.hidguardian": hidguardian,
            "hidapi": hidapi,
        }
        factory = PyDualSenseFactory(platform="win32")
        with patch.dict(sys.modules, modules):
            first_adapter = factory.connect()
            self.assertEqual(first_adapter.identity.serial, "AA:BB:CC")
            self.assertEqual(first_adapter.identity.vendor_id, 0x054C)
            self.assertEqual(first_adapter.identity.product_id, 0x0CE6)
            first_adapter.close()
            devices[:] = [first, second]
            second_adapter = factory.connect()
            self.assertEqual(second_adapter.identity.serial, "AA:BB:CC")
            second_adapter.close()

        self.assertEqual(opened, [b"hid-path-a", b"hid-path-a"])

    def test_factory_prefers_windows_usb_gamepad_interface(self):
        other_interface = FakeHidInfo(b"hid-path-a", interface_number=0)
        gamepad_interface = FakeHidInfo(b"hid-path-z", interface_number=3)
        opened = []

        package = types.ModuleType("pydualsense")
        package.pydualsense = StableRaw
        enums = types.ModuleType("pydualsense.enums")
        enums.ConnectionType = ConnectionType
        hidguardian = types.ModuleType("pydualsense.hidguardian")
        hidguardian.check_hide = lambda: False
        package.hidguardian = hidguardian
        hidapi = types.ModuleType("hidapi")
        hidapi.enumerate = lambda **_kwargs: [other_interface, gamepad_interface]
        hidapi.Device = lambda *, info: (opened.append(info.path) or FakeHidDevice(info))

        with patch.dict(
            sys.modules,
            {
                "pydualsense": package,
                "pydualsense.enums": enums,
                "pydualsense.hidguardian": hidguardian,
                "hidapi": hidapi,
            },
        ):
            adapter = PyDualSenseFactory(platform="win32").connect()
            adapter.close()

        self.assertEqual(opened, [b"hid-path-z"])


if __name__ == "__main__":
    unittest.main()
