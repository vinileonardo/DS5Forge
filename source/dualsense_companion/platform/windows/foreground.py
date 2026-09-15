"""Win32 foreground-window adapter.

All ctypes/Win32 process inspection stays in this module. Failures are
returned as recoverable diagnostics instead of escaping the polling worker.
"""

from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from typing import Any

from ...domain.games import ForegroundApplication

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class WindowsForegroundDetector:
    def current(self) -> ForegroundApplication:
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return ForegroundApplication.desktop(
                now=time.time(),
                diagnostic="Win32 foreground APIs are unavailable on this platform.",
            )
        user32 = windll.user32
        _configure_user32(user32)
        observed_at = time.time()
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ForegroundApplication.desktop(now=observed_at, diagnostic="No foreground window is available.")

        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_id = int(pid.value) if pid.value else None
        executable_path, path_diagnostic = _process_path(process_id, windll)
        executable_name = os.path.basename(executable_path) if executable_path else None
        title = _window_title(user32, hwnd)
        diagnostics = path_diagnostic
        return ForegroundApplication(
            available=True,
            pid=process_id,
            executable_name=executable_name,
            executable_path=executable_path,
            title=title,
            observed_at=observed_at,
            process_alive=process_id is not None,
            diagnostic=diagnostics,
        )

    read = current


def _window_title(user32: Any, hwnd: int) -> str | None:
    try:
        length = int(user32.GetWindowTextLengthW(hwnd))
        buffer = ctypes.create_unicode_buffer(max(1, length + 1))
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        return buffer.value or None
    except Exception:
        return None


def _process_path(process_id: int | None, windll: Any) -> tuple[str | None, str | None]:
    if process_id is None:
        return None, "Foreground window did not expose a process id."
    kernel32 = windll.kernel32
    _configure_kernel32(kernel32)
    # QueryFullProcessImageNameW only needs limited query rights. Requesting
    # PROCESS_VM_READ as well causes avoidable access-denied failures for
    # protected/elevated games and would prevent executable matching entirely.
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
    if not handle:
        return None, "Process path unavailable (access denied or process exited)."
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None, "Process path unavailable (access denied or process exited)."
        return buffer.value or None, None if buffer.value else "Process path was empty."
    except Exception as exc:
        return None, f"Process path inspection failed: {exc}"
    finally:
        kernel32.CloseHandle(handle)


def _configure_user32(user32: Any) -> None:
    """Declare pointer-sized Win32 signatures before calling them.

    ``ctypes`` defaults an undeclared function result to ``c_int``. That
    truncates HWND values on 64-bit Windows and can make foreground detection
    fail nondeterministically.
    """

    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int


def _configure_kernel32(kernel32: Any) -> None:
    """Declare process APIs whose handles are pointer-sized on 64-bit Windows."""

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
