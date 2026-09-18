#!/usr/bin/env python3
"""Read-only Windows XInput slot probe for DS5Forge live diagnostics."""

from __future__ import annotations

import ctypes
import json
import sys
from ctypes import wintypes

ERROR_SUCCESS = 0
ERROR_DEVICE_NOT_CONNECTED = 1167


class XInputGamepad(ctypes.Structure):
    _fields_ = [
        ("buttons", wintypes.WORD),
        ("left_trigger", wintypes.BYTE),
        ("right_trigger", wintypes.BYTE),
        ("left_x", ctypes.c_short),
        ("left_y", ctypes.c_short),
        ("right_x", ctypes.c_short),
        ("right_y", ctypes.c_short),
    ]


class XInputState(ctypes.Structure):
    _fields_ = [("packet_number", wintypes.DWORD), ("gamepad", XInputGamepad)]


def main() -> int:
    if sys.platform != "win32":
        print(json.dumps({"ok": False, "error": "Windows runtime required"}))
        return 2

    dll = ctypes.WinDLL("xinput1_4.dll")
    get_state = dll.XInputGetState
    get_state.argtypes = [wintypes.DWORD, ctypes.POINTER(XInputState)]
    get_state.restype = wintypes.DWORD

    slots = []
    for index in range(4):
        state = XInputState()
        code = int(get_state(index, ctypes.byref(state)))
        connected = code == ERROR_SUCCESS
        slot = {"slot": index, "connected": connected, "result": code}
        if connected:
            slot.update(
                {
                    "packet_number": int(state.packet_number),
                    "buttons": int(state.gamepad.buttons),
                    "left_trigger": int(state.gamepad.left_trigger),
                    "right_trigger": int(state.gamepad.right_trigger),
                    "left_x": int(state.gamepad.left_x),
                    "left_y": int(state.gamepad.left_y),
                    "right_x": int(state.gamepad.right_x),
                    "right_y": int(state.gamepad.right_y),
                }
            )
        elif code != ERROR_DEVICE_NOT_CONNECTED:
            slot["unexpected_error"] = True
        slots.append(slot)

    print(json.dumps({"ok": True, "connected_count": sum(1 for item in slots if item["connected"]), "slots": slots}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
