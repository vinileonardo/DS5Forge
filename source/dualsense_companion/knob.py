"""Neumorphic rotary knob widget (drag vertically to turn)."""

import math
import tkinter as tk

import customtkinter as ctk

START_ANGLE = 225.0  # degrees, lower-left
SWEEP = 270.0  # total travel, gap at the bottom


class Knob(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        label,
        lo,
        hi,
        step,
        value,
        command,
        face="#eaeef6",
        track="#d3dbea",
        accent="#4d8bf0",
        text="#3f4a5a",
        edge="#ffffff",
        size=104,
    ):
        super().__init__(parent, fg_color=face, corner_radius=18)
        self.lo, self.hi, self.step = lo, hi, step
        self.command = command
        self.accent, self.track, self.face, self.text_color = accent, track, face, text
        self.edge = edge
        self.value = value
        self.size = size

        self.canvas = tk.Canvas(self, width=size, height=size, highlightthickness=0, bg=face, bd=0)
        self.canvas.pack(padx=6, pady=(8, 0))
        self.name = ctk.CTkLabel(self, text=label, text_color=text, font=ctk.CTkFont(size=11), wraplength=size + 10)
        self.name.pack(padx=4, pady=(0, 8))

        self.canvas.bind("<Button-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self._render()

    def _frac(self):
        return (self.value - self.lo) / (self.hi - self.lo) if self.hi > self.lo else 0.0

    def _fmt(self):
        return str(int(round(self.value)) if self.step >= 1 else round(self.value, 4))

    def _render(self):
        c = self.canvas
        c.delete("all")
        s = self.size
        cx = cy = s / 2
        r = s / 2 - 10
        frac = max(0.0, min(1.0, self._frac()))

        # sunken track ring
        c.create_arc(
            cx - r, cy - r, cx + r, cy + r, start=START_ANGLE, extent=-SWEEP, style="arc", outline=self.track, width=8
        )
        # accent value ring
        if frac > 0:
            c.create_arc(
                cx - r,
                cy - r,
                cx + r,
                cy + r,
                start=START_ANGLE,
                extent=-SWEEP * frac,
                style="arc",
                outline=self.accent,
                width=8,
            )
        # raised knob body
        br = r - 12
        c.create_oval(cx - br, cy - br, cx + br, cy + br, fill=self.face, outline=self.edge, width=2)
        c.create_oval(cx - br, cy - br + 3, cx + br, cy + br + 3, outline=self.track, width=1)
        # indicator dot
        theta = math.radians(START_ANGLE - SWEEP * frac)
        dx = cx + (r - 4) * math.cos(theta)
        dy = cy - (r - 4) * math.sin(theta)
        c.create_oval(dx - 4, dy - 4, dx + 4, dy + 4, fill=self.accent, outline="")
        # value text
        c.create_text(cx, cy, text=self._fmt(), fill=self.text_color, font=("Segoe UI", 13, "bold"))

    def _press(self, e):
        self._press_y = e.y
        self._press_val = self.value

    def _drag(self, e):
        span = self.hi - self.lo
        delta = (self._press_y - e.y) / 150.0 * span
        self._apply(self._press_val + delta)

    def _wheel(self, e):
        self._apply(self.value + (self.step if e.delta > 0 else -self.step))

    def _apply(self, raw):
        raw = max(self.lo, min(self.hi, raw))
        value = int(round(raw)) if self.step >= 1 else round(round(raw / self.step) * self.step, 4)
        if value != self.value:
            self.value = value
            self._render()
            if self.command:
                self.command(value)

    def set(self, value):
        self.value = max(self.lo, min(self.hi, value))
        self._render()
