import unittest
from unittest.mock import MagicMock, patch

from dualsense_companion.app import ApplicationRuntime


class FakeFacade:
    def __init__(self):
        self.start_calls = 0
        self.stop_calls = 0

    def start(self):
        self.start_calls += 1

    def stop(self):
        self.stop_calls += 1


class ApplicationRuntimeTests(unittest.TestCase):
    def test_runtime_coordinates_core_and_api_once(self):
        facade = FakeFacade()
        server = MagicMock()
        with patch("dualsense_companion.api.server.LocalApiServer", return_value=server):
            runtime = ApplicationRuntime(facade, host="127.0.0.1", port=8765)
            runtime.start()
            runtime.start()
            runtime.stop()

        self.assertEqual(facade.start_calls, 1)
        self.assertEqual(facade.stop_calls, 1)
        server.start.assert_called_once_with()
        server.stop.assert_called_once_with()

    def test_runtime_rejects_external_bind_before_start(self):
        facade = FakeFacade()
        with self.assertRaises(ValueError):
            ApplicationRuntime(facade, host="0.0.0.0")
        self.assertEqual(facade.start_calls, 0)

    def test_runtime_rejects_invalid_port_before_start(self):
        facade = FakeFacade()
        with self.assertRaises(ValueError):
            ApplicationRuntime(facade, port=0)
        self.assertEqual(facade.start_calls, 0)


if __name__ == "__main__":
    unittest.main()
