"""Control panel: neumorphic soft-UI with light, dark, and liquid-glass themes."""

import os
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from . import paths
from .diagnostics.logging import get_logger
from .domain.errors import DS5ForgeError
from .knob import Knob

LOGGER = get_logger(__name__)

THEMES = {
    "Light": {
        "mode": "light",
        "alpha": 1.0,
        "bg": "#f2f3f5",
        "card": "#ffffff",
        "sunk": "#e7e9ee",
        "accent": "#e0322d",
        "accent_dark": "#b61f1b",
        "text": "#1c1f26",
        "muted": "#8a90a0",
        "edge": "#ffffff",
        "knob_face": "#1f2229",
        "knob_text": "#ffffff",
        "knob_track": "#3c414c",
    },
    "Dark": {
        "mode": "dark",
        "alpha": 1.0,
        "bg": "#161719",
        "card": "#212226",
        "sunk": "#111214",
        "accent": "#e5322d",
        "accent_dark": "#ff5a54",
        "text": "#eceef2",
        "muted": "#8a90a0",
        "edge": "#33353d",
        "knob_face": "#0d0e10",
        "knob_text": "#ffffff",
        "knob_track": "#3a3d45",
    },
    "Liquid Glass": {
        "mode": "dark",
        "alpha": 0.89,
        "bg": "#2c2e34",
        "card": "#3a3d45",
        "sunk": "#2a2c32",
        "accent": "#ef4444",
        "accent_dark": "#ff6b6b",
        "text": "#f1f2f5",
        "muted": "#a6acba",
        "edge": "#565a66",
        "knob_face": "#232529",
        "knob_text": "#ffffff",
        "knob_track": "#4a4e58",
    },
}

# key, label, min, max, step, rebuild-audio-on-change
RUMBLE_PARAMS = [
    ("gate", "Silence gate", 0.0, 0.30, 0.005, False),
    ("impact_level", "Impact level (full rumble)", 0.20, 1.00, 0.01, False),
    ("gamma", "Curve sharpness", 1.0, 4.0, 0.1, False),
    ("transient_min_level", "Hit detection threshold", 0.0, 0.60, 0.01, False),
    ("transient_gain", "Hit punch amount", 0.0, 6.0, 0.1, False),
    ("transient_weight", "Hit vs. loudness blend", 0.0, 1.0, 0.05, False),
    ("drive_gate", "Faint-result cutoff", 0.0, 0.30, 0.01, False),
    ("min_rumble", "Minimum rumble on a hit", 0, 150, 1, False),
    ("max_rumble", "Maximum rumble", 100, 255, 1, False),
    ("texture_gate_mult", "Small-motor gate mult.", 1.0, 2.5, 0.1, False),
    ("heavy_cutoff_hz", "Deep-bass cutoff (Hz)", 60, 300, 5, True),
    ("texture_center_hz", "Texture band center (Hz)", 150, 600, 10, True),
    ("fast_attack_ms", "Response attack (ms)", 1, 30, 1, True),
    ("fast_release_ms", "Response release (ms)", 40, 400, 5, True),
    ("baseline_attack_ms", "Baseline attack (ms)", 100, 800, 10, True),
    ("baseline_release_ms", "Baseline release (ms)", 500, 4000, 50, True),
]

TRACKPAD_PARAMS = [
    ("pointer_speed", "Pointer speed", 0.1, 3.0, 0.05),
    ("accel_cap", "Acceleration cap", 0.0, 3.0, 0.1),
    ("acceleration", "Acceleration strength", 0.0, 0.05, 0.002),
    ("scroll_speed", "Scroll speed", 0.1, 1.5, 0.05),
]


class ControlPanel(ctk.CTk):
    def __init__(self, facade, on_quit):
        theme_name = facade.config().get("theme", "Light")
        self.pal = THEMES.get(theme_name, THEMES["Light"])
        ctk.set_appearance_mode(self.pal["mode"])
        super().__init__(fg_color=self.pal["bg"])
        self.facade = facade
        self.on_quit = on_quit
        self.theme_name = theme_name
        self.title("DualSense Companion")
        self.geometry("600x820")
        self.minsize(560, 700)
        self.attributes("-alpha", self.pal["alpha"])
        icon = paths.resource_path(os.path.join("resources", "app.ico"))
        if os.path.exists(icon):
            try:
                self.iconbitmap(icon)
            except Exception as exc:
                # A missing optional icon must not prevent the legacy UI from opening.
                LOGGER.debug("optional window icon could not be loaded: %s", exc)
        self.protocol("WM_DELETE_WINDOW", self._quit)

        self._knobs = {}
        self._build_all()
        self.after(150, self._tick)

    # ---- build / rebuild ----
    def _build_all(self):
        self._knobs = {}
        self._build_header()
        self._build_tabs()
        self._build_profile_bar()

    def _rebuild(self):
        for w in (getattr(self, "_header", None), getattr(self, "_tabsw", None), getattr(self, "_profile_card", None)):
            if w is not None:
                w.destroy()
        self.configure(fg_color=self.pal["bg"])
        self._build_all()

    def _card(self, parent):
        return ctk.CTkFrame(
            parent, fg_color=self.pal["card"], corner_radius=22, border_width=1, border_color=self.pal["edge"]
        )

    # ---- header ----
    def _build_header(self):
        p = self.pal
        self._header = self._card(self)
        self._header.pack(fill="x", padx=16, pady=(16, 8))
        inner = ctk.CTkFrame(self._header, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=16)

        self.status_var = tk.StringVar(value="Starting…")
        ctk.CTkLabel(
            inner, textvariable=self.status_var, text_color=p["text"], font=ctk.CTkFont(size=15, weight="bold")
        ).pack(anchor="w")
        self.device_var = tk.StringVar(value="")
        ctk.CTkLabel(inner, textvariable=self.device_var, text_color=p["muted"], font=ctk.CTkFont(size=12)).pack(
            anchor="w", pady=(0, 10)
        )

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        snapshot = self.facade.snapshot()
        self.rumble_on = tk.BooleanVar(value=snapshot.rumble_enabled)
        self.trackpad_on = tk.BooleanVar(value=snapshot.touchpad_enabled)
        ctk.CTkSwitch(
            row,
            text="Rumble",
            variable=self.rumble_on,
            onvalue=True,
            offvalue=False,
            command=self._apply_toggles,
            text_color=p["text"],
            progress_color=p["accent"],
        ).pack(side="left")
        ctk.CTkSwitch(
            row,
            text="Trackpad",
            variable=self.trackpad_on,
            onvalue=True,
            offvalue=False,
            command=self._apply_toggles,
            text_color=p["text"],
            progress_color=p["accent"],
        ).pack(side="left", padx=(24, 0))
        ctk.CTkButton(
            row,
            text="Test rumble",
            width=110,
            command=self._test_rumble,
            fg_color=p["accent"],
            hover_color=p["accent_dark"],
            corner_radius=16,
        ).pack(side="right")

        meters = ctk.CTkFrame(inner, fg_color="transparent")
        meters.pack(fill="x", pady=(14, 0))
        ctk.CTkLabel(meters, text="L", text_color=p["muted"], width=14).pack(side="left")
        self.meter_l = ctk.CTkProgressBar(
            meters, progress_color=p["accent"], fg_color=p["sunk"], height=12, corner_radius=6
        )
        self.meter_l.set(0)
        self.meter_l.pack(side="left", fill="x", expand=True, padx=(4, 14))
        ctk.CTkLabel(meters, text="R", text_color=p["muted"], width=14).pack(side="left")
        self.meter_r = ctk.CTkProgressBar(
            meters, progress_color=p["accent"], fg_color=p["sunk"], height=12, corner_radius=6
        )
        self.meter_r.set(0)
        self.meter_r.pack(side="left", fill="x", expand=True, padx=(4, 0))

    # ---- tabs ----
    def _build_tabs(self):
        p = self.pal
        self._tabsw = ctk.CTkTabview(
            self,
            fg_color=p["card"],
            segmented_button_fg_color=p["sunk"],
            segmented_button_selected_color=p["accent"],
            segmented_button_selected_hover_color=p["accent_dark"],
            text_color=p["text"],
            corner_radius=22,
        )
        self._tabsw.pack(fill="both", expand=True, padx=16, pady=8)
        self._tabsw.add("Rumble")
        self._tabsw.add("Trackpad")
        self._tabsw.add("Controls")

        rumble = ctk.CTkScrollableFrame(self._tabsw.tab("Rumble"), fg_color="transparent")
        rumble.pack(fill="both", expand=True)
        self._grid_knobs(rumble, "rumble", RUMBLE_PARAMS, cols=3)

        track = self._tabsw.tab("Trackpad")
        knob_wrap = ctk.CTkFrame(track, fg_color="transparent")
        knob_wrap.pack(fill="x")
        self._grid_knobs(knob_wrap, "trackpad", TRACKPAD_PARAMS, cols=3)
        config = self.facade.config()
        self.tap_var = tk.BooleanVar(value=config["trackpad"].get("tap_to_click", True))
        ctk.CTkSwitch(
            track,
            text="Tap touchpad to click",
            variable=self.tap_var,
            onvalue=True,
            offvalue=False,
            text_color=p["text"],
            progress_color=p["accent"],
            command=lambda: self._set("trackpad", "tap_to_click", self.tap_var.get()),
        ).pack(anchor="w", pady=14, padx=6)

        ctrl = self._tabsw.tab("Controls")
        ctk.CTkLabel(ctrl, text="Theme", text_color=p["text"], font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", pady=(6, 6)
        )
        self.theme_seg = ctk.CTkSegmentedButton(
            ctrl,
            values=list(THEMES.keys()),
            command=self._apply_theme,
            selected_color=p["accent"],
            selected_hover_color=p["accent_dark"],
            fg_color=p["sunk"],
            text_color=p["text"],
        )
        self.theme_seg.set(self.theme_name)
        self.theme_seg.pack(anchor="w", fill="x", pady=(0, 16))

        ctk.CTkLabel(
            ctrl, text="Mic button toggles", text_color=p["text"], font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", pady=(0, 6))
        current = {"master": "Both", "rumble": "Rumble", "trackpad": "Trackpad"}.get(
            config.get("mic_button", "master"), "Both"
        )
        self.mic_seg = ctk.CTkSegmentedButton(
            ctrl,
            values=["Both", "Rumble", "Trackpad"],
            command=self._apply_mic,
            selected_color=p["accent"],
            selected_hover_color=p["accent_dark"],
            fg_color=p["sunk"],
            text_color=p["text"],
        )
        self.mic_seg.set(current)
        self.mic_seg.pack(anchor="w", fill="x", pady=(0, 16))
        ctk.CTkLabel(
            ctrl,
            justify="left",
            text_color=p["muted"],
            font=ctk.CTkFont(size=12),
            text="L3 (left stick click)  =  left mouse button\n"
            "R3 (right stick click)  =  right mouse button\n"
            "1 finger  =  move    •    tap  =  click\n"
            "2 fingers  =  scroll    •    2-finger tap  =  right click",
        ).pack(anchor="w")

    def _grid_knobs(self, parent, section, params, cols):
        p = self.pal
        for i in range(cols):
            parent.grid_columnconfigure(i, weight=1)
        for idx, item in enumerate(params):
            key, label, lo, hi, step = item[0], item[1], item[2], item[3], item[4]
            structural = item[5] if len(item) > 5 else False
            cur = self.facade.config()[section][key]
            knob = Knob(
                parent,
                label,
                lo,
                hi,
                step,
                cur,
                command=lambda v, s=section, k=key, rb=structural: self._set(s, k, v, rebuild=rb),
                face=p["knob_face"],
                track=p["knob_track"],
                accent=p["accent"],
                text=p["knob_text"],
                edge=p["knob_face"],
            )
            knob.grid(row=idx // cols, column=idx % cols, padx=8, pady=8, sticky="nsew")
            self._knobs[(section, key)] = knob

    def _push_config_to_knobs(self):
        for (section, key), knob in self._knobs.items():
            val = self.facade.config()[section].get(key)
            if val is not None:
                knob.set(val)

    # ---- profile bar ----
    def _build_profile_bar(self):
        p = self.pal
        self._profile_card = self._card(self)
        self._profile_card.pack(fill="x", padx=16, pady=(8, 16))
        bar = ctk.CTkFrame(self._profile_card, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(bar, text="Profile", text_color=p["text"]).pack(side="left", padx=(0, 8))
        self.profile_menu = ctk.CTkOptionMenu(
            bar,
            values=["Default"],
            command=self._load_profile,
            fg_color=p["accent"],
            button_color=p["accent_dark"],
            button_hover_color=p["accent_dark"],
            width=150,
        )
        self.profile_menu.pack(side="left")
        ctk.CTkButton(
            bar,
            text="Save as…",
            width=80,
            command=self._save_profile_as,
            fg_color=p["sunk"],
            text_color=p["text"],
            hover_color=p["accent_dark"],
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            bar,
            text="Delete",
            width=64,
            command=self._delete_profile,
            fg_color=p["sunk"],
            text_color=p["text"],
            hover_color=p["accent_dark"],
        ).pack(side="left")
        ctk.CTkButton(
            bar,
            text="Save settings",
            width=110,
            command=self._save_config,
            fg_color=p["accent"],
            hover_color=p["accent_dark"],
        ).pack(side="right")
        self._refresh_profiles()

    # ---- state plumbing ----
    def _set(self, section, key, value, rebuild=False):
        try:
            self.facade.update_config({section: {key: value}}, persist=False)
        except DS5ForgeError as exc:
            messagebox.showerror("Invalid setting", exc.message)

    def _apply_toggles(self):
        self.facade.set_rumble_enabled(self.rumble_on.get())
        self.facade.set_touchpad_enabled(self.trackpad_on.get())

    def _apply_mic(self, choice):
        try:
            self.facade.update_config(
                {"mic_button": {"Both": "master", "Rumble": "rumble", "Trackpad": "trackpad"}[choice]}, persist=False
            )
        except DS5ForgeError as exc:
            messagebox.showerror("Invalid setting", exc.message)

    def _apply_theme(self, name):
        self.theme_name = name
        self.pal = THEMES[name]
        try:
            self.facade.update_config({"theme": name}, persist=False)
        except DS5ForgeError as exc:
            messagebox.showerror("Invalid setting", exc.message)
            return
        ctk.set_appearance_mode(self.pal["mode"])
        self.attributes("-alpha", self.pal["alpha"])
        self._rebuild()

    def _test_rumble(self):
        if not self.facade.snapshot().health.controller_available:
            messagebox.showinfo("Test rumble", "Controller not connected.")
            return
        try:
            if not self.facade.test_rumble():
                messagebox.showinfo("Test rumble", "Controller not connected.")
        except DS5ForgeError as exc:
            messagebox.showerror("Test rumble failed", exc.message)

    def _tick(self):
        snapshot = self.facade.snapshot()
        if snapshot.connection.value == "connected":
            self.status_var.set(f"Controller connected    •    battery {snapshot.battery.level}%")
        elif snapshot.connection.value in {"connecting", "reconnecting"}:
            self.status_var.set("Waiting for controller (connect via USB)…")
        elif snapshot.connection.value == "error":
            self.status_var.set("Controller service error — retrying…")
        else:
            self.status_var.set("Waiting for controller (connect via USB)…")
        self.device_var.set(f"Listening on: {snapshot.audio.device}" if snapshot.audio.device else "")
        self.meter_l.set(snapshot.motors.left / 255)
        self.meter_r.set(snapshot.motors.right / 255)
        self.rumble_on.set(snapshot.rumble_enabled)
        self.trackpad_on.set(snapshot.touchpad_enabled)
        self.after(120, self._tick)

    # ---- profiles ----
    def _refresh_profiles(self):
        names = [profile["name"] for profile in self.facade.profiles()]
        self.profile_menu.configure(values=names or ["Default"])

    def _load_profile(self, name):
        try:
            self.facade.load_profile(name)
            self._push_config_to_knobs()
        except DS5ForgeError as exc:
            messagebox.showerror("Profile load failed", exc.message)

    def _save_profile_as(self):
        dialog = ctk.CTkInputDialog(text="Profile name:", title="Save profile")
        name = dialog.get_input()
        if not name:
            return
        safe = "".join(c for c in name if c not in '\\/:*?"<>|').strip()
        if not safe:
            return
        try:
            self.facade.save_profile(safe)
            self._refresh_profiles()
            self.profile_menu.set(safe)
        except DS5ForgeError as exc:
            messagebox.showerror("Profile save failed", exc.message)

    def _delete_profile(self):
        name = self.profile_menu.get()
        if name == "Default":
            messagebox.showinfo("Delete", "The Default profile can't be deleted.")
            return
        if messagebox.askyesno("Delete", f"Delete profile '{name}'?"):
            try:
                self.facade.delete_profile(name)
            except DS5ForgeError as exc:
                messagebox.showerror("Delete failed", exc.message)
                return
            self._refresh_profiles()
            self.profile_menu.set("Default")

    def _save_config(self):
        try:
            self.facade.save_config()
            messagebox.showinfo("Saved", "Settings saved. They'll load automatically next time.")
        except DS5ForgeError as exc:
            messagebox.showerror("Save failed", exc.message)

    def _quit(self):
        self.on_quit()
        self.destroy()
