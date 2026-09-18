#!/usr/bin/env python3
from __future__ import annotations

import ctypes
import json
import os
import sys
from ctypes import wintypes
from typing import Any

SONY_VENDOR_ID = 0x054C
DUALSENSE_PRODUCT_IDS = {0x0CE6, 0x0DF2}

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


def _win32_open_probe(path: str, share_mode: int) -> dict[str, Any]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        path,
        GENERIC_READ | GENERIC_WRITE,
        share_mode,
        None,
        OPEN_EXISTING,
        FILE_FLAG_OVERLAPPED,
        None,
    )
    raw_handle = ctypes.cast(handle, ctypes.c_void_p).value
    error = ctypes.get_last_error()
    opened = raw_handle not in (None, INVALID_HANDLE_VALUE)
    if opened:
        kernel32.CloseHandle(handle)
    return {"opened": opened, "win32_error": error}


def main() -> int:
    package_dir = os.path.join(sys.prefix, "Lib", "site-packages", "pydualsense")
    os.add_dll_directory(package_dir)
    os.environ["PATH"] = package_dir + os.pathsep + os.environ.get("PATH", "")

    import hidapi  # type: ignore[import-not-found]

    results: list[dict[str, Any]] = []
    for info in hidapi.enumerate(vendor_id=SONY_VENDOR_ID):
        product_id = int(getattr(info, "product_id", 0) or 0)
        if product_id not in DUALSENSE_PRODUCT_IDS:
            continue
        path = getattr(info, "path", None)
        path_text = path.decode("utf-8", errors="replace") if isinstance(path, bytes) else str(path)
        entry: dict[str, Any] = {
            "path": path_text,
            "product_id": product_id,
            "interface_number": int(getattr(info, "interface_number", -1) or -1),
            "descriptor_serial": getattr(info, "serial_number", None),
            "feature_09_hex": None,
            "opened": False,
            "report_received": False,
            "report_length": 0,
            "error": None,
            "win32_shared_rw": _win32_open_probe(path_text, FILE_SHARE_READ | FILE_SHARE_WRITE),
            "win32_exclusive_rw": _win32_open_probe(path_text, 0),
        }
        try:
            device = hidapi.Device(info=info, blocking=False)
            entry["opened"] = True
            try:
                try:
                    feature = device.get_feature_report(0x09, 32)
                    entry["feature_09_hex"] = bytes(feature).hex()
                except Exception:
                    pass
                report = device.read(128, timeout_ms=400, blocking=False)
                if report:
                    entry["report_received"] = True
                    entry["report_length"] = len(report)
            finally:
                device.close()
        except Exception as exc:  # diagnostic probe only
            entry["error"] = str(exc)
        results.append(entry)

    print(json.dumps({"ok": True, "devices": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
