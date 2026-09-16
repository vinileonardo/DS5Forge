import json
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import pytest

from dualsense_companion.core.config import ConfigRepository
from dualsense_companion.core.facade import CoreFacade
from dualsense_companion.core.games_repository import GameRegistryRepository
from dualsense_companion.core.input_isolation import InputIsolationCoordinator
from dualsense_companion.domain.errors import DS5ForgeError, ErrorCode
from dualsense_companion.platform.windows.hidhide import WindowsHidHideIsolationProvider

DEVICE = r"HID\VID_054C&PID_0CE6&MI_03\8&1121ad8a&0&0000"
BASE = r"USB\VID_054C&PID_0CE6\6&28CF390B&0&5"


class FakeHidHideRunner:
    def __init__(self, *, fail_once: str | None = None) -> None:
        self.cloak = False
        self.apps: set[str] = set()
        self.hidden: set[str] = set()
        self.calls: list[tuple[str, ...]] = []
        self.fail_once = fail_once

    def __call__(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        args = tuple(command[1:])
        self.calls.append(args)
        op = args[0]
        if self.fail_once == op:
            self.fail_once = None
            return subprocess.CompletedProcess(command, 1, stdout="", stderr=f"forced {op} failure")
        if op == "--version":
            return self._ok(command, "1.5.230\n")
        if op == "--cloak-state":
            return self._ok(command, "--cloak-on\n" if self.cloak else "--cloak-off\n")
        if op == "--app-list":
            return self._ok(command, "".join(f'--app-reg "{item}"\n' for item in sorted(self.apps)))
        if op == "--dev-list":
            return self._ok(command, "".join(f'--dev-hide "{item}"\n' for item in sorted(self.hidden)))
        if op == "--dev-gaming":
            return self._ok(
                command,
                json.dumps(
                    [
                        {
                            "friendlyName": "Sony Interactive Entertainment DualSense Wireless Controller",
                            "devices": [
                                {
                                    "present": True,
                                    "gamingDevice": True,
                                    "product": "DualSense Wireless Controller",
                                    "deviceInstancePath": DEVICE,
                                    "baseContainerDeviceInstancePath": BASE,
                                }
                            ],
                        }
                    ]
                ),
            )
        if op == "--app-reg":
            self.apps.add(args[1])
            return self._ok(command)
        if op == "--app-unreg":
            self.apps.discard(args[1])
            return self._ok(command)
        if op == "--dev-hide":
            self.hidden.add(args[1])
            return self._ok(command)
        if op == "--dev-unhide":
            self.hidden.discard(args[1])
            return self._ok(command)
        if op == "--cloak-on":
            self.cloak = True
            return self._ok(command)
        if op == "--cloak-off":
            self.cloak = False
            return self._ok(command)
        return subprocess.CompletedProcess(command, 2, stdout="", stderr=f"unsupported {op}")

    @staticmethod
    def _ok(command: list[str], stdout: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")


class ConcurrentGuardRunner(FakeHidHideRunner):
    def __init__(self) -> None:
        super().__init__()
        self._guard = threading.Lock()
        self.active = 0
        self.max_active = 0

    def __call__(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        with self._guard:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.02)
            return super().__call__(command)
        finally:
            with self._guard:
                self.active -= 1


class FakeControllerFactory:
    def connect(self):
        raise AssertionError("controller connection is not expected")


class FakeMouse:
    def move(self, dx, dy):
        return None

    def button(self, left, down):
        return None

    def wheel(self, amount, horizontal=False):
        return None

    def release_all(self):
        return None


def make_provider(root: Path, runner: FakeHidHideRunner) -> WindowsHidHideIsolationProvider:
    cli = root / "HidHideCLI.exe"
    app = root / "ds5forge-core.exe"
    cli.write_bytes(b"fixture")
    app.write_bytes(b"fixture")
    return WindowsHidHideIsolationProvider(
        cli_path=cli,
        application_path=app,
        state_path=root / "hidhide-isolation.json",
        runner=runner,
        platform="win32",
    )


def make_facade(root: Path, isolation: InputIsolationCoordinator) -> CoreFacade:
    config = ConfigRepository(
        config_path=root / "config.json",
        bundled_config_path=Path("source/dualsense_companion/resources/default_config.json"),
        bundled_profiles_dir=Path("source/dualsense_companion/resources/profiles"),
        user_profiles_dir=root / "profiles",
    )
    return CoreFacade(
        controller_factory=FakeControllerFactory(),
        mouse_output=FakeMouse(),
        config_repository=config,
        games_repository=GameRegistryRepository(path=root / "games.json"),
        input_isolation=isolation,
    )


def test_hidhide_provider_serializes_concurrent_cli_sessions():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        runner = ConcurrentGuardRunner()
        provider = make_provider(root, runner)
        results: list[object] = []

        threads = [
            threading.Thread(target=lambda: results.append(provider.capability())),
            threading.Thread(target=lambda: results.append(provider.status())),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)

        assert all(not thread.is_alive() for thread in threads)
        assert len(results) == 2
        assert runner.max_active == 1


def test_hidhide_isolation_is_transactional_and_restores_only_owned_state():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        runner = FakeHidHideRunner()
        provider = make_provider(root, runner)

        capability = provider.capability()
        assert capability.operational is True
        assert capability.device_instance_path == DEVICE

        active = provider.enable()
        assert active.active is True
        assert active.physical_input_visible is False
        assert active.application_registered is True
        assert active.device_hidden is True
        assert active.cloak_enabled is True
        assert provider.state_path.is_file()

        disabled = provider.disable()
        assert disabled.active is False
        assert disabled.physical_input_visible is True
        assert runner.cloak is False
        assert runner.apps == set()
        assert runner.hidden == set()
        assert not provider.state_path.exists()


def test_hidhide_enable_rolls_back_if_cloak_activation_fails():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        runner = FakeHidHideRunner(fail_once="--cloak-on")
        provider = make_provider(root, runner)

        with pytest.raises(RuntimeError, match="forced --cloak-on failure"):
            provider.enable()

        assert runner.cloak is False
        assert runner.apps == set()
        assert runner.hidden == set()
        assert not provider.state_path.exists()


def test_hidhide_recovers_stale_owned_session_on_next_start():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        runner = FakeHidHideRunner()
        first = make_provider(root, runner)
        assert first.enable().active is True

        restarted = make_provider(root, runner)
        assert restarted.recover_stale() is True
        assert runner.cloak is False
        assert runner.apps == set()
        assert runner.hidden == set()
        assert restarted.status().active is False


def test_remap_input_isolation_updates_duplicate_input_state_and_releases_on_native():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        runner = FakeHidHideRunner()
        provider = make_provider(root, runner)
        facade = make_facade(root, InputIsolationCoordinator(provider))
        try:
            with pytest.raises(DS5ForgeError) as raised:
                facade.enable_input_isolation()
            assert raised.value.code is ErrorCode.INPUT_ISOLATION_UNAVAILABLE

            remap = facade.update_compatibility("remap")
            assert remap["double_input_risk"] is True

            isolated = facade.enable_input_isolation()
            assert isolated["active"] is True
            assert facade.compatibility()["physical_input_visible"] is False
            assert facade.compatibility()["physical_suppression_active"] is True
            assert facade.compatibility()["double_input_risk"] is False
            diagnostic = facade.duplicate_input_diagnostics()
            assert diagnostic["risk"] is False
            assert diagnostic["suppression_verified"] is True

            native = facade.update_compatibility("native")
            assert native["double_input_risk"] is False
            assert native["physical_input_visible"] is True
            assert runner.cloak is False
            assert runner.apps == set()
            assert runner.hidden == set()
        finally:
            facade.stop()
