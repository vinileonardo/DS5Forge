"""Best-effort Windows process-name inspection for conflict diagnostics."""

from __future__ import annotations

import ctypes
import time
from collections.abc import Iterable
from ctypes import wintypes

from ...domain.games import ForegroundApplication

TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class WindowsProcessInspector:
    def running_processes(self) -> set[str] | None:
        records = _snapshot_processes()
        if records is None:
            return None
        return {name for _, name in records}

    def running_applications(
        self,
        executable_names: Iterable[str] | None = None,
    ) -> tuple[ForegroundApplication, ...] | None:
        """Return live process identities for registered game lifecycle checks.

        Full image paths are queried only for requested executable names so the
        foreground poll does not open every process on the machine. Path lookup
        is best-effort; executable name + PID remain available when Windows
        denies access to the image path.
        """

        records = _snapshot_processes()
        if records is None:
            return None
        expected = {str(name).casefold() for name in executable_names or () if str(name).strip()}
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return None
        kernel32 = windll.kernel32
        _configure_process_query(kernel32)
        observed_at = time.time()
        result: list[ForegroundApplication] = []
        for pid, name in records:
            if expected and name.casefold() not in expected:
                continue
            result.append(
                ForegroundApplication(
                    available=True,
                    pid=pid,
                    executable_name=name,
                    executable_path=_query_process_image_path(kernel32, pid),
                    title=None,
                    observed_at=observed_at,
                    process_alive=True,
                )
            )
        return tuple(result)


def _snapshot_processes() -> tuple[tuple[int, str], ...] | None:
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return None
    kernel32 = windll.kernel32
    _configure_kernel32(kernel32)
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot in (None, INVALID_HANDLE_VALUE):
        return None
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    records: list[tuple[int, str]] = []
    try:
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return None
        while True:
            if entry.szExeFile:
                records.append((int(entry.th32ProcessID), str(entry.szExeFile)))
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
        return tuple(records)
    finally:
        kernel32.CloseHandle(snapshot)


def _configure_kernel32(kernel32) -> None:
    """Declare Toolhelp signatures so HANDLE values stay pointer-sized."""

    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL


def _configure_process_query(kernel32) -> None:
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL


def _query_process_image_path(kernel32, pid: int) -> str | None:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return None
    try:
        capacity = 32768
        buffer = ctypes.create_unicode_buffer(capacity)
        size = wintypes.DWORD(capacity)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return buffer.value[: int(size.value)] or None
    finally:
        kernel32.CloseHandle(handle)
