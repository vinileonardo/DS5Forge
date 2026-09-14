"""Use the DualSense touchpad and stick clicks as a mouse."""

import ctypes
import threading
import time

ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ULONG_PTR)]


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


def _send(flags, dx=0, dy=0, data=0):
    inp = INPUT(type=0)
    inp.mi = MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, None)
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def mouse_move(dx, dy):
    _send(MOUSEEVENTF_MOVE, int(dx), int(dy))


def mouse_button(left, down):
    flags = {(True, True): MOUSEEVENTF_LEFTDOWN, (True, False): MOUSEEVENTF_LEFTUP,
             (False, True): MOUSEEVENTF_RIGHTDOWN, (False, False): MOUSEEVENTF_RIGHTUP}
    _send(flags[(left, down)])


def mouse_wheel(amount, horizontal=False):
    _send(MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL, data=int(amount))


class TouchMouseEngine(threading.Thread):
    POLL_HZ = 250
    TAP_MAX_MS = 220
    TAP_MAX_MOVE = 40

    def __init__(self, state):
        super().__init__(daemon=True, name="TouchMouse")
        self.state = state
        self.stop_flag = threading.Event()

        self._reset_touch_state()
        self.prev_l3 = self.prev_r3 = False
        self.prev_mic = False
        self.prev_pad_click = False
        self.scroll_accum_v = 0.0
        self.scroll_accum_h = 0.0

    @property
    def cfg(self):
        return self.state.config["trackpad"]

    def _reset_touch_state(self):
        self.prev_active0 = False
        self.prev_active1 = False
        self.last_x = self.last_y = None
        self.touch_start_t = 0.0
        self.touch_travel = 0.0
        self.two_finger_session = False
        self.last2_y = self.last2_x = None

    def _feedback_pulse(self):
        ds = self.state.ds
        if ds is None:
            return
        try:
            ds.setRightMotor(140)
            time.sleep(0.12)
            ds.setRightMotor(0)
        except Exception:
            pass

    def run(self):
        dt = 1.0 / self.POLL_HZ
        while not self.stop_flag.is_set():
            try:
                self._poll()
            except Exception:
                time.sleep(0.5)
            time.sleep(dt)

    def _poll(self):
        ds = self.state.ds
        if ds is None:
            return
        s = ds.state

        mic = bool(getattr(s, "micBtn", False))
        if mic and not self.prev_mic:
            self.state.toggle(self.state.config.get("mic_button", "master"))
            threading.Thread(target=self._feedback_pulse, daemon=True).start()
        self.prev_mic = mic

        l3, r3 = bool(s.L3), bool(s.R3)
        if l3 != self.prev_l3:
            mouse_button(True, l3)
        if r3 != self.prev_r3:
            mouse_button(False, r3)
        self.prev_l3, self.prev_r3 = l3, r3

        if not self.state.trackpad_enabled:
            self.prev_active0 = self.prev_active1 = False
            return

        pad_click = bool(getattr(s, "touchBtn", False))
        if pad_click != self.prev_pad_click:
            mouse_button(True, pad_click)
        self.prev_pad_click = pad_click

        t0, t1 = s.trackPadTouch0, s.trackPadTouch1
        a0, a1 = bool(t0.isActive), bool(t1.isActive)
        now = time.monotonic()

        if a0 and a1:
            self.two_finger_session = True
            cy = (t0.Y + t1.Y) / 2.0
            cx = (t0.X + t1.X) / 2.0
            if self.last2_y is not None:
                self.scroll_accum_v += (self.last2_y - cy) * self.cfg["scroll_speed"]
                self.scroll_accum_h += (cx - self.last2_x) * self.cfg["scroll_speed"]
                for accum, horiz in ((self.scroll_accum_v, False),
                                     (self.scroll_accum_h, True)):
                    while abs(accum) >= 40:
                        step = 40 if accum > 0 else -40
                        mouse_wheel(step, horizontal=horiz)
                        accum -= step
                    if horiz:
                        self.scroll_accum_h = accum
                    else:
                        self.scroll_accum_v = accum
            self.last2_y, self.last2_x = cy, cx
            self.last_x = self.last_y = None
        else:
            self.last2_y = self.last2_x = None

        if a0 and not a1:
            if not self.prev_active0 or self.last_x is None:
                self.touch_start_t = now
                self.touch_travel = 0.0
            else:
                dx = t0.X - self.last_x
                dy = t0.Y - self.last_y
                self.touch_travel += abs(dx) + abs(dy)
                speed = (dx * dx + dy * dy) ** 0.5
                accel = 1.0 + min(speed * self.cfg["acceleration"],
                                  self.cfg.get("accel_cap", 1.2))
                mouse_move(dx * self.cfg["pointer_speed"] * accel,
                           dy * self.cfg["pointer_speed"] * accel)
            self.last_x, self.last_y = t0.X, t0.Y
        else:
            self.last_x = self.last_y = None

        if self.prev_active0 and not a0 and not a1:
            dur_ms = (now - self.touch_start_t) * 1000
            if dur_ms < self.TAP_MAX_MS and self.touch_travel < self.TAP_MAX_MOVE \
                    and self.cfg.get("tap_to_click", True):
                left = not self.two_finger_session
                mouse_button(left, True)
                mouse_button(left, False)
            self.two_finger_session = False

        self.prev_active0, self.prev_active1 = a0, a1

    def stop(self):
        self.stop_flag.set()
