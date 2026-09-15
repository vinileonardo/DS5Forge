"""Windows ``SendInput`` keyboard adapter with explicit ownership."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from ...domain.errors import DS5ForgeError, ErrorCode, PlatformUnavailableError

ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class INPUT(ctypes.Structure):
    class _I(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    _anonymous_ = ("i",)
    _fields_ = [("type", wintypes.DWORD), ("i", _I)]


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
MAX_COMBO_KEYS = 4

_SPECIAL_KEYS = {
    "BACKSPACE": 0x08,
    "TAB": 0x09,
    "ENTER": 0x0D,
    "SHIFT": 0x10,
    "CTRL": 0x11,
    "ALT": 0x12,
    "PAUSE": 0x13,
    "CAPSLOCK": 0x14,
    "ESC": 0x1B,
    "SPACE": 0x20,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "END": 0x23,
    "HOME": 0x24,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
    "WIN": 0x5B,
}
_SPECIAL_KEYS.update({f"F{index}": 0x6F + index for index in range(1, 13)})
_KEY_ALIASES = {
    "CONTROL": "CTRL",
    "ESCAPE": "ESC",
    "RETURN": "ENTER",
    "WINDOWS": "WIN",
}


class WindowsKeyboardOutput:
    """Own mapped keyboard outputs without releasing another mapping's keys.

    Output codes may be a single key (``SPACE``) or a bounded combination such
    as ``CTRL+SHIFT+S``. Physical key ownership is reference counted so two
    active outputs that share ``CTRL`` cannot release each other's modifier.
    """

    def __init__(self) -> None:
        self._held_outputs: dict[str, tuple[str, ...]] = {}
        self._key_refcounts: dict[str, int] = {}

    def key(self, code: str, down: bool) -> None:
        canonical, keys = _parse_key_output(code)
        if down:
            if canonical in self._held_outputs:
                return
            self._press_output(canonical, keys)
            return
        self._release_output(canonical)

    def release_all(self) -> None:
        failures: list[Exception] = []
        for code in tuple(self._held_outputs):
            try:
                self._release_output(code)
            except Exception as exc:
                failures.append(exc)
        if failures:
            raise failures[0]

    def _press_output(self, canonical: str, keys: tuple[str, ...]) -> None:
        acquired: list[str] = []
        try:
            for key in keys:
                count = self._key_refcounts.get(key, 0)
                if count == 0:
                    self._send(_virtual_key(key), True)
                self._key_refcounts[key] = count + 1
                acquired.append(key)
        except Exception:
            remaining = self._rollback_press(acquired)
            if remaining:
                self._held_outputs[canonical] = remaining
            raise
        self._held_outputs[canonical] = keys

    def _rollback_press(self, acquired: list[str]) -> tuple[str, ...]:
        remaining: list[str] = []
        for key in reversed(acquired):
            count = self._key_refcounts.get(key, 0)
            if count > 1:
                self._key_refcounts[key] = count - 1
                continue
            if count != 1:
                continue
            try:
                self._send(_virtual_key(key), False)
            except Exception:
                remaining.append(key)
                continue
            self._key_refcounts.pop(key, None)
        remaining.reverse()
        return tuple(remaining)

    def _release_output(self, canonical: str) -> None:
        remaining = self._held_outputs.get(canonical)
        if not remaining:
            return
        failed: list[str] = []
        failures: list[Exception] = []
        for key in reversed(remaining):
            count = self._key_refcounts.get(key, 0)
            if count > 1:
                self._key_refcounts[key] = count - 1
                continue
            if count != 1:
                continue
            try:
                self._send(_virtual_key(key), False)
            except Exception as exc:
                failed.append(key)
                failures.append(exc)
                continue
            self._key_refcounts.pop(key, None)
        if failed:
            failed.reverse()
            self._held_outputs[canonical] = tuple(failed)
            raise failures[0]
        self._held_outputs.pop(canonical, None)

    @staticmethod
    def _send(vk: int, down: bool) -> None:
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            raise PlatformUnavailableError(
                "Windows SendInput is unavailable on this platform.",
                detail="ctypes.windll.user32 is not present",
            )
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.ki = KEYBDINPUT(vk, 0, 0 if down else KEYEVENTF_KEYUP, 0, None)
        result = windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        if result != 1:
            raise DS5ForgeError(ErrorCode.SYNTHETIC_OUTPUT_FAILED, "Windows keyboard output failed.")


def _parse_key_output(code: str) -> tuple[str, tuple[str, ...]]:
    raw_parts = str(code).split("+")
    if not 1 <= len(raw_parts) <= MAX_COMBO_KEYS:
        raise DS5ForgeError(
            ErrorCode.SYNTHETIC_OUTPUT_FAILED,
            "Keyboard output combination is invalid.",
            fields={"code": code, "max_keys": MAX_COMBO_KEYS},
        )
    keys: list[str] = []
    seen: set[str] = set()
    for raw in raw_parts:
        normalized = _KEY_ALIASES.get(raw.strip().upper(), raw.strip().upper())
        if not normalized:
            raise DS5ForgeError(
                ErrorCode.SYNTHETIC_OUTPUT_FAILED,
                "Keyboard output combination contains an empty key.",
                fields={"code": code},
            )
        _virtual_key(normalized)
        if normalized in seen:
            raise DS5ForgeError(
                ErrorCode.SYNTHETIC_OUTPUT_FAILED,
                "Keyboard output combination contains a duplicate key.",
                fields={"code": code, "key": normalized},
            )
        seen.add(normalized)
        keys.append(normalized)
    return "+".join(keys), tuple(keys)


def _virtual_key(code: str) -> int:
    if code in _SPECIAL_KEYS:
        return _SPECIAL_KEYS[code]
    if len(code) == 1 and "A" <= code <= "Z":
        return ord(code)
    if len(code) == 1 and "0" <= code <= "9":
        return ord(code)
    raise DS5ForgeError(
        ErrorCode.SYNTHETIC_OUTPUT_FAILED,
        "Keyboard output code is invalid.",
        fields={"code": code},
    )
