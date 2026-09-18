"""Least-privilege HidHide integration for explicit Remap input isolation.

The adapter uses only the fixed HidHide CLI installed by Nefarius. It never
installs a driver, searches PATH, invokes a shell, or treats HidHide as a
virtual-controller provider. Changes are transactional and a small ownership
marker lets the next DS5Forge start recover configuration after an unclean exit.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...domain.input_isolation import InputIsolationCapability, InputIsolationStatus

HIDHIDE_CLI = Path(r"C:\Program Files\Nefarius Software Solutions\HidHide\x64\HidHideCLI.exe")
DS5FORGE_CORE_BASENAME = "ds5forge-core.exe"
SONY_VENDOR_ID = "VID_054C"

Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


@dataclass(frozen=True, slots=True)
class ExclusiveSuppressionCapability:
    available: bool
    verified: bool
    session_scoped: bool
    reason: str | None = None


class WindowsHidHideIsolationProvider:
    """Own only the HidHide entries created for the current DS5Forge session."""

    def __init__(
        self,
        *,
        cli_path: Path = HIDHIDE_CLI,
        application_path: Path | None = None,
        state_path: Path | None = None,
        runner: Runner | None = None,
        platform: str | None = None,
        clock: Callable[[], float] = time.time,
        target_hid_path_getter: Callable[[], object | None] | None = None,
    ) -> None:
        self.cli_path = Path(cli_path)
        self.application_path = Path(application_path or sys.executable)
        self.state_path = state_path or _default_state_path()
        self.runner = runner
        self.platform = platform or sys.platform
        self.clock = clock
        self.target_hid_path_getter = target_hid_path_getter
        self._lock = threading.RLock()

    def capability(self) -> InputIsolationCapability:
        with self._lock:
            return self._capability_locked()

    def _capability_locked(self) -> InputIsolationCapability:
        if self.platform != "win32":
            return InputIsolationCapability(reason="Physical input isolation is available only on Windows.")
        if not self.cli_path.is_file():
            return InputIsolationCapability(
                installed=False,
                available=False,
                executable=str(self.cli_path),
                application_path=str(self.application_path),
                reason="HidHide is not installed in the expected system location.",
            )
        if self.application_path.name.casefold() != DS5FORGE_CORE_BASENAME:
            return InputIsolationCapability(
                installed=True,
                available=False,
                version=self._version(),
                executable=str(self.cli_path),
                application_path=str(self.application_path),
                reason="Input isolation requires the packaged ds5forge-core.exe process.",
            )
        if not self.application_path.is_file():
            return InputIsolationCapability(
                installed=True,
                available=False,
                version=self._version(),
                executable=str(self.cli_path),
                application_path=str(self.application_path),
                reason="The packaged DS5Forge core executable could not be verified on disk.",
            )
        try:
            devices = self._gaming_devices()
        except Exception as exc:
            return InputIsolationCapability(
                installed=True,
                available=False,
                version=self._version(),
                executable=str(self.cli_path),
                application_path=str(self.application_path),
                reason=f"HidHide device discovery failed: {exc}",
            )
        wired = _wired_dualsense_devices(devices)
        if len(wired) > 1 and self.target_hid_path_getter is not None:
            selected = _normalize_hid_instance(self.target_hid_path_getter())
            if selected:
                matched = [
                    device
                    for device in wired
                    if _normalize_hid_instance(device.get("deviceInstancePath")) == selected
                ]
                if len(matched) == 1:
                    wired = matched
        if len(wired) != 1:
            reason = (
                "No wired DualSense was found by HidHide."
                if not wired
                else "More than one wired DualSense is connected and the active DS5Forge HID path could not be resolved."
            )
            return InputIsolationCapability(
                installed=True,
                available=True,
                version=self._version(),
                executable=str(self.cli_path),
                application_path=str(self.application_path),
                device_detected=False,
                reason=reason,
            )
        device = wired[0]
        instance = str(device.get("deviceInstancePath") or "").strip()
        return InputIsolationCapability(
            installed=True,
            available=True,
            version=self._version(),
            executable=str(self.cli_path),
            application_path=str(self.application_path),
            device_detected=bool(instance),
            device_instance_path=instance or None,
            reason=None if instance else "The wired DualSense device instance path is unavailable.",
        )

    def status(self) -> InputIsolationStatus:
        with self._lock:
            return self._status_locked()

    def _status_locked(self) -> InputIsolationStatus:
        capability = self._capability_locked()
        if not capability.installed:
            return InputIsolationStatus(capability=capability, reason=capability.reason, updated_at=self.clock())
        try:
            cloak = self._cloak_enabled()
            applications = self._applications()
            hidden = self._hidden_devices()
        except Exception as exc:
            return InputIsolationStatus(
                capability=capability,
                reason="HidHide status could not be verified.",
                last_error=str(exc),
                updated_at=self.clock(),
            )
        app_registered = _normalize_path(str(self.application_path)) in applications
        target = (capability.device_instance_path or "").casefold()
        device_hidden = bool(target and target in hidden)
        active = bool(capability.operational and cloak and app_registered and device_hidden)
        physical_visible = not (cloak and device_hidden)
        if active:
            reason = "Physical DualSense input is isolated from ordinary applications while DS5Forge remains allowed."
        elif cloak and device_hidden and not app_registered:
            reason = "The DualSense is hidden, but DS5Forge is not allowlisted in HidHide."
        else:
            reason = capability.reason or "Physical DualSense input remains visible to ordinary applications."
        return InputIsolationStatus(
            active=active,
            owned=self.state_path.is_file(),
            cloak_enabled=cloak,
            application_registered=app_registered,
            device_hidden=device_hidden,
            physical_input_visible=physical_visible,
            double_input_risk=not active,
            device_instance_path=capability.device_instance_path,
            capability=capability,
            reason=reason,
            updated_at=self.clock(),
        )

    def enable(self) -> InputIsolationStatus:
        with self._lock:
            return self._enable_locked()

    def _enable_locked(self) -> InputIsolationStatus:
        capability = self._capability_locked()
        if not capability.operational or capability.device_instance_path is None:
            raise RuntimeError(capability.reason or "HidHide input isolation is unavailable")
        before = self._status_locked()
        if before.active:
            return before
        marker = {
            "application_path": str(self.application_path),
            "device_instance_path": capability.device_instance_path,
            "application_was_registered": before.application_registered,
            "device_was_hidden": before.device_hidden,
            "cloak_was_enabled": before.cloak_enabled,
        }
        self._write_marker(marker)
        try:
            if not before.application_registered:
                self._run("--app-reg", str(self.application_path))
            if not before.device_hidden:
                self._run("--dev-hide", capability.device_instance_path)
            if not before.cloak_enabled:
                self._run("--cloak-on")
            verified = self._status_locked()
            if not verified.active:
                raise RuntimeError(verified.last_error or verified.reason or "HidHide isolation verification failed")
            return verified
        except Exception:
            self._restore_marker(marker)
            self._delete_marker()
            raise

    def disable(self) -> InputIsolationStatus:
        with self._lock:
            return self._disable_locked()

    def _disable_locked(self) -> InputIsolationStatus:
        marker = self._read_marker()
        if marker is None:
            return self._status_locked()
        try:
            self._restore_marker(marker)
        finally:
            self._delete_marker()
        return self._status_locked()

    def recover_stale(self) -> bool:
        with self._lock:
            marker = self._read_marker()
            if marker is None:
                return False
            self._disable_locked()
            return True

    def _restore_marker(self, marker: dict[str, Any]) -> None:
        application = str(marker.get("application_path") or "")
        device = str(marker.get("device_instance_path") or "")
        failures: list[str] = []
        # Turn off a cloak we enabled before removing its allowlist/device
        # entries, preventing a partially restored state from hiding input.
        if not bool(marker.get("cloak_was_enabled")):
            try:
                self._run("--cloak-off")
            except Exception as exc:
                failures.append(f"cloak: {exc}")
        if device and not bool(marker.get("device_was_hidden")):
            try:
                self._run("--dev-unhide", device)
            except Exception as exc:
                failures.append(f"device: {exc}")
        if application and not bool(marker.get("application_was_registered")):
            try:
                self._run("--app-unreg", application)
            except Exception as exc:
                failures.append(f"application: {exc}")
        if failures:
            raise RuntimeError("; ".join(failures))

    def _version(self) -> str | None:
        try:
            output = self._run("--version")
        except Exception:
            return None
        return output.strip().splitlines()[0].strip() if output.strip() else None

    def _cloak_enabled(self) -> bool:
        return "--cloak-on" in self._run("--cloak-state").casefold()

    def _applications(self) -> set[str]:
        result: set[str] = set()
        for line in self._run("--app-list").splitlines():
            value = _quoted_value(line, "--app-reg")
            if value:
                result.add(_normalize_path(value))
        return result

    def _hidden_devices(self) -> set[str]:
        result: set[str] = set()
        for line in self._run("--dev-list").splitlines():
            value = _quoted_value(line, "--dev-hide")
            if value:
                result.add(value.casefold())
        return result

    def _gaming_devices(self) -> list[dict[str, Any]]:
        payload = json.loads(self._run("--dev-gaming"))
        devices: list[dict[str, Any]] = []
        for container in payload if isinstance(payload, list) else []:
            if not isinstance(container, dict):
                continue
            for device in container.get("devices", []):
                if isinstance(device, dict):
                    devices.append(device)
        return devices

    def _run(self, *arguments: str) -> str:
        command = [str(self.cli_path), *arguments]
        if self.runner is not None:
            completed = self.runner(command)
        else:
            completed = _run_external_windows_command(command, timeout=5.0)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "HidHideCLI failed").strip()
            raise RuntimeError(detail)
        return completed.stdout or ""

    def _write_marker(self, marker: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(json.dumps(marker, indent=2), encoding="utf-8")
        os.replace(temporary, self.state_path)

    def _read_marker(self) -> dict[str, Any] | None:
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError):
            return None
        return raw if isinstance(raw, dict) else None

    def _delete_marker(self) -> None:
        try:
            self.state_path.unlink()
        except FileNotFoundError:
            pass


class WindowsHidHideExclusiveSuppressionProvider:
    """Adapt the proven P5.1 HidHide isolation provider to Exclusive ownership.

    Exclusive and Remap intentionally share one HidHide authority. This keeps
    active-controller selection, application allowlisting, rollback markers and
    stale recovery in one place instead of letting a privileged virtual-device
    broker mutate HidHide independently.
    """

    def __init__(self, isolation: WindowsHidHideIsolationProvider) -> None:
        self.isolation = isolation
        self._owner: tuple[str, int] | None = None
        self._lock = threading.RLock()

    def capability(self) -> ExclusiveSuppressionCapability:
        capability = self.isolation.capability()
        operational = capability.operational
        return ExclusiveSuppressionCapability(
            available=operational,
            verified=operational,
            session_scoped=operational,
            reason=None if operational else capability.reason,
        )

    def enable(self, *, token: str, generation: int) -> None:
        owner = (token, generation)
        with self._lock:
            if self._owner is not None and self._owner != owner:
                raise RuntimeError("HidHide suppression is already owned by another Exclusive session")
            status = self.isolation.enable()
            if not status.active or status.physical_input_visible:
                raise RuntimeError(status.last_error or status.reason or "HidHide suppression could not be verified")
            self._owner = owner

    def heartbeat(self, *, token: str, generation: int) -> None:
        owner = (token, generation)
        with self._lock:
            if self._owner != owner:
                raise RuntimeError("Exclusive HidHide suppression ownership was lost")
            status = self.isolation.status()
            if not status.active or status.physical_input_visible:
                raise RuntimeError(status.last_error or status.reason or "Exclusive HidHide suppression is no longer active")

    def disable(self, *, token: str, generation: int) -> None:
        owner = (token, generation)
        with self._lock:
            if self._owner is not None and self._owner != owner:
                raise RuntimeError("Exclusive HidHide suppression ownership does not match")
            try:
                status = self.isolation.disable()
                if status.active or not status.physical_input_visible:
                    raise RuntimeError(status.last_error or status.reason or "HidHide suppression teardown could not be verified")
            finally:
                self._owner = None

    def recover_stale(self) -> None:
        with self._lock:
            self.isolation.recover_stale()
            self._owner = None


def _run_external_windows_command(command: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    """Launch a system executable without leaking PyInstaller's DLL directory.

    PyInstaller one-file adjusts the process DLL search directory to its
    extraction directory. Windows child processes inherit that setting at
    CreateProcess time, which can make unrelated system/vendor tools load the
    wrong DLLs or hang. Clear it only for process creation, then restore the
    parent immediately while the child completes normally.
    """

    with _clean_child_dll_directory():
        process = subprocess.Popen(  # noqa: S603 - fixed absolute HidHide CLI; no shell
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout=stdout, stderr=stderr)


@contextmanager
def _clean_child_dll_directory() -> Iterator[None]:
    if sys.platform != "win32":
        yield
        return
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        yield
        return
    kernel32 = windll.kernel32
    get_directory = kernel32.GetDllDirectoryW
    set_directory = kernel32.SetDllDirectoryW
    get_directory.argtypes = [ctypes.c_uint32, ctypes.c_wchar_p]
    get_directory.restype = ctypes.c_uint32
    set_directory.argtypes = [ctypes.c_wchar_p]
    set_directory.restype = ctypes.c_int
    buffer = ctypes.create_unicode_buffer(32768)
    length = int(get_directory(len(buffer), buffer))
    previous = buffer.value if 0 < length < len(buffer) else None
    changed = bool(set_directory(None))
    try:
        yield
    finally:
        if changed:
            set_directory(previous)


def _wired_dualsense_devices(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for device in devices:
        instance = str(device.get("deviceInstancePath") or "").upper()
        base = str(device.get("baseContainerDeviceInstancePath") or "").upper()
        product = str(device.get("product") or "").casefold()
        if not bool(device.get("present")) or not bool(device.get("gamingDevice")):
            continue
        if SONY_VENDOR_ID not in instance or not base.startswith("USB\\"):
            continue
        if "dualsense" not in product:
            continue
        result.append(device)
    return result


def _normalize_hid_instance(value: object | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    upper = text.upper().strip()
    marker = upper.find("HID#")
    if marker >= 0:
        upper = upper[marker:]
        upper = upper.split("#{", 1)[0]
        upper = upper.replace("#", "\\")
    else:
        marker = upper.find("HID\\")
        if marker >= 0:
            upper = upper[marker:]
    return upper.rstrip("\\")


def _quoted_value(line: str, command: str) -> str | None:
    stripped = line.strip()
    if not stripped.casefold().startswith(command.casefold()):
        return None
    first = stripped.find('"')
    last = stripped.rfind('"')
    if first < 0 or last <= first:
        return None
    return stripped[first + 1 : last]


def _normalize_path(value: str) -> str:
    return value.replace("/", "\\").rstrip("\\").casefold()


def _default_state_path() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "DS5Forge" / "hidhide-isolation.json"
    return Path.home() / ".ds5forge" / "hidhide-isolation.json"
