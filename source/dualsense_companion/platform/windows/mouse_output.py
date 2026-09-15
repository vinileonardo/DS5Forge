"""Windows SendInput adapter with deterministic button release."""

from __future__ import annotations

import ctypes
import threading

from ...domain.errors import DS5ForgeError, ErrorCode, PlatformUnavailableError

ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class INPUT(ctypes.Structure):
    class _I(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]

    _anonymous_ = ("i",)
    _fields_ = [("type", ctypes.c_ulong), ("i", _I)]


MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x01000
XBUTTON1 = 0x0001
XBUTTON2 = 0x0002


class WindowsMouseOutput:
    def __init__(self) -> None:
        self._button_refcounts: dict[str, int] = {}
        self._left_down = False
        self._right_down = False
        self._extra_down: set[str] = set()
        self._button_lock = threading.RLock()

    def move(self, dx: int, dy: int) -> None:
        self._send(MOUSEEVENTF_MOVE, int(dx), int(dy))

    def button(self, left: bool, down: bool) -> None:
        self._button_named("left" if left else "right", down)

    def button_code(self, code: str, down: bool) -> None:
        """Send a named mapped button, including Mouse4/Mouse5."""

        normalized = _normalize_button_code(code)
        self._button_named(normalized, down)

    def wheel(self, amount: int, horizontal: bool = False) -> None:
        self._send(MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL, data=int(amount))

    def release_all(self) -> None:
        # Force every physically held button up regardless of how many local
        # owners currently reference it. Failed key-ups retain their counts so
        # a later teardown can retry deterministically.
        errors: list[Exception] = []
        with self._button_lock:
            for code in tuple(self._button_refcounts):
                try:
                    flags, data = _button_event(code, False)
                    self._send(flags, data=data)
                except Exception as exc:
                    errors.append(exc)
                    continue
                self._button_refcounts.pop(code, None)
                self._sync_button_state(code)
        if errors:
            raise errors[0]

    def _button_named(self, code: str, down: bool) -> None:
        with self._button_lock:
            owners = self._button_refcounts.get(code, 0)
            if down:
                if owners == 0:
                    flags, data = _button_event(code, True)
                    self._send(flags, data=data)
                self._button_refcounts[code] = owners + 1
                self._sync_button_state(code)
                return
            if owners <= 0:
                return
            if owners > 1:
                self._button_refcounts[code] = owners - 1
                self._sync_button_state(code)
                return
            flags, data = _button_event(code, False)
            self._send(flags, data=data)
            self._button_refcounts.pop(code, None)
            self._sync_button_state(code)

    def _sync_button_state(self, code: str) -> None:
        down = self._button_refcounts.get(code, 0) > 0
        if code == "left":
            self._left_down = down
        elif code == "right":
            self._right_down = down
        elif down:
            self._extra_down.add(code)
        else:
            self._extra_down.discard(code)

    @staticmethod
    def _send(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> None:
        user32 = getattr(ctypes, "windll", None)
        if user32 is None:
            raise PlatformUnavailableError(
                "Windows SendInput is unavailable on this platform.",
                detail="ctypes.windll.user32 is not present",
            )
        inp = INPUT(type=0)
        inp.mi = MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, None)
        result = user32.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        if result != 1:
            raise DS5ForgeError(ErrorCode.POINTER_OUTPUT_FAILED, "Windows mouse output failed.")


def _normalize_button_code(code: str) -> str:
    normalized = str(code).strip().casefold()
    aliases = {
        "left": "left",
        "left_button": "left",
        "lmb": "left",
        "right": "right",
        "right_button": "right",
        "rmb": "right",
        "middle": "middle",
        "middle_button": "middle",
        "mmb": "middle",
        "mouse4": "mouse4",
        "x1": "mouse4",
        "xbutton1": "mouse4",
        "mouse5": "mouse5",
        "x2": "mouse5",
        "xbutton2": "mouse5",
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise DS5ForgeError(
            ErrorCode.SYNTHETIC_OUTPUT_FAILED,
            "Mouse output code is invalid.",
            fields={"code": code, "allowed": ["left", "right", "middle", "mouse4", "mouse5"]},
        ) from exc


def _button_event(code: str, down: bool) -> tuple[int, int]:
    if code == "left":
        return (MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP, 0)
    if code == "right":
        return (MOUSEEVENTF_RIGHTDOWN if down else MOUSEEVENTF_RIGHTUP, 0)
    if code == "middle":
        return (MOUSEEVENTF_MIDDLEDOWN if down else MOUSEEVENTF_MIDDLEUP, 0)
    if code == "mouse4":
        return (MOUSEEVENTF_XDOWN if down else MOUSEEVENTF_XUP, XBUTTON1)
    if code == "mouse5":
        return (MOUSEEVENTF_XDOWN if down else MOUSEEVENTF_XUP, XBUTTON2)
    raise AssertionError(f"unsupported normalized mouse button: {code}")
