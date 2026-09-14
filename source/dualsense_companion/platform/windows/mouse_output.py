"""Windows SendInput adapter with deterministic button release."""

from __future__ import annotations

import ctypes

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
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x01000


class WindowsMouseOutput:
    def __init__(self) -> None:
        self._left_down = False
        self._right_down = False

    def move(self, dx: int, dy: int) -> None:
        self._send(MOUSEEVENTF_MOVE, int(dx), int(dy))

    def button(self, left: bool, down: bool) -> None:
        flags = {
            (True, True): MOUSEEVENTF_LEFTDOWN,
            (True, False): MOUSEEVENTF_LEFTUP,
            (False, True): MOUSEEVENTF_RIGHTDOWN,
            (False, False): MOUSEEVENTF_RIGHTUP,
        }
        self._send(flags[(left, down)])
        if left:
            self._left_down = down
        else:
            self._right_down = down

    def wheel(self, amount: int, horizontal: bool = False) -> None:
        self._send(MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL, data=int(amount))

    def release_all(self) -> None:
        # Use tracked state so shutdown never synthesizes unnecessary clicks,
        # but attempt every held release even when one SendInput call fails.
        errors: list[Exception] = []
        if self._left_down:
            try:
                self.button(True, False)
            except Exception as exc:
                errors.append(exc)
        if self._right_down:
            try:
                self.button(False, False)
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise errors[0]

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
