"""Control panel: neumorphic soft-UI with light, dark, and liquid-glass themes."""

import json
import os
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from . import paths
from .knob import Knob

THEMES = {
    "Light": {
        "mode": "light", "alpha": 1.0,
        "bg": "#f2f3f5", "card": "#ffffff", "sunk": "#e7e9ee",
        "accent": "#e0322d", "accent_dark": "#b61f1b",
        "text": "#1c1f26", "muted": "#8a90a0", "edge": "#ffffff",
        "knob_face": "#1f2229", "knob_text": "#ffffff", "knob_track": "#3c414c",
    },
    "Dark": {
        "mode": "dark", "alpha": 1.0,
        "bg": "#161719", "card": "#212226", "sunk": "#111214",
        "accent": "#e5322d", "accent_dark": "#ff5a54",
        "text": "#eceef2", "muted": "#8a90a0", "edge": "#33353d",
        "knob_face": "#0d0e10", "knob_text": "#ffffff", "knob_track": "#3a3d45",
    },
    "Liquid Glass": {
        "mode": "dark", "alpha": 0.89,
        "bg": "#2c2e34", "card": "#3a3d45", "sunk": "#2a2c32",
        "accent": "#ef4444", "accent_dark": "#ff6b6b",
        "text": "#f1f2f5", "muted": "#a6acba", "edge": "#565a66",
        "knob_face": "#232529", "knob_text": "#ffffff", "knob_track": "#4a4e58",
    },
}

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
    def __init__(self, state, on_quit):
        theme_name = state.config.get("theme", "Light")
        self.pal = THEMES.get(theme_name, THEMES["Light"])
        ctk.set_appearance_mode(self.pal["mode"])
        super().__init__(fg_color=self.pal["bg"])
        self.state_obj = state
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
            except Exception:
                pass
        self.protocol("WM_DELETE_WINDOW", self._quit)

        self._knobs = {}
        self._build_all()
        self.after(150, self._tick)

    def _build_all(self):
        self._knobs = {}
        self._build_header()
        self._build_tabs()
        self._build_profile_bar()

    def _rebuild(self):
        for w in (getattr(self, "_header", None), getattr(self, "_tabsw", None),
                  getattr(self, "_profile_card", None)):
            if w is not None:
                w.destroy()
        self.configure(fg_color=self.pal["bg"])
        self._build_all()

    def _card(self, parent):
        return ctk.CTkFrame(parent, fg_color=self.pal["card"], corner_radius=22,
                            border_width=1, border_color=self.pal["edge"])

    def _build_header(self):
        p = self.pal
        self._header = self._card(self)
        self._header.pack(fill="x", padx=16, pady=(16, 8))
        inner = ctk.CTkFrame(self._header, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=16)

        self.status_var = tk.StringVar(value="Starting…")
        ctk.CTkLabel(inner, textvariable=self.status_var, text_color=p["text"],
                     font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w")
        self.device_var = tk.StringVar(value="")
        ctk.CTkLabel(inner, textvariable=self.device_var, text_color=p["muted"],
                     font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(0, 10))

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        self.rumble_on = tk.BooleanVar(value=self.state_obj.rumble_enabled)
        self.trackpad_on = tk.BooleanVar(value=self.state_obj.trackpad_enabled)
        ctk.CTkSwitch(row, text="Rumble", variable=self.rumble_on, onvalue=True,
                      offvalue=False, command=self._apply_toggles, text_color=p["text"],
                      progress_color=p["accent"]).pack(side="left")
        ctk.CTkSwitch(row, text="Trackpad", variable=self.trackpad_on, onvalue=True,
                      offvalue=False, command=self._apply_toggles, text_color=p["text"],
                      progress_color=p["accent"]).pack(side="left", padx=(24, 0))
        ctk.CTkButton(row, text="Test rumble", width=110, command=self._test_rumble,
                      fg_color=p["accent"], hover_color=p["accent_dark"], corner_radius=16
                      ).pack(side="right")

        meters = ctk.CTkFrame(inner, fg_color="transparent")
        meters.pack(fill="x", pady=(14, 0))
        ctk.CTkLabel(meters, text="L", text_color=p["muted"], width=14).pack(side="left")
        self.meter_l = ctk.CTkProgressBar(meters, progress_color=p["accent"],
                                          fg_color=p["sunk"], height=12, corner_radius=6)
        self.meter_l.set(0)
        self.meter_l.pack(side="left", fill="x", expand=True, padx=(4, 14))
        ctk.CTkLabel(meters, text="R", text_color=p["muted"], width=14).pack(side="left")
        self.meter_r = ctk.CTkProgressBar(meters, progress_color=p["accent"],
                                          fg_color=p["sunk"], height=12, corner_radius=6)
        self.meter_r.set(0)
        self.meter_r.pack(side="left", fill="x", expand=True, padx=(4, 0))

    def _build_tabs(self):
        p = self.pal
        self._tabsw = ctk.CTkTabview(self, fg_color=p["card"], segmented_button_fg_color=p["sunk"],
                                     segmented_button_selected_color=p["accent"],
                                     segmented_button_selected_hover_color=p["accent_dark"],
                                     text_color=p["text"], corner_radius=22)
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
        self.tap_var = tk.BooleanVar(value=self.state_obj.config["trackpad"].get("tap_to_click", True))
        ctk.CTkSwitch(track, text="Tap touchpad to click", variable=self.tap_var,
                      onvalue=True, offvalue=False, text_color=p["text"], progress_color=p["accent"],
                      command=lambda: self._set("trackpad", "tap_to_click", self.tap_var.get())
                      ).pack(anchor="w", pady=14, padx=6)

        ctrl = self._tabsw.tab("Controls")
        ctk.CTkLabel(ctrl, text="Theme", text_color=p["text"],
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(6, 6))
        self.theme_seg = ctk.CTkSegmentedButton(
            ctrl, values=list(THEMES.keys()), command=self._apply_theme,
            selected_color=p["accent"], selected_hover_color=p["accent_dark"],
            fg_color=p["sunk"], text_color=p["text"])
        self.theme_seg.set(self.theme_name)
        self.theme_seg.pack(anchor="w", fill="x", pady=(0, 16))

        ctk.CTkLabel(ctrl, text="Mic button toggles", text_color=p["text"],
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(0, 6))
        current = {"master": "Both", "rumble": "Rumble", "trackpad": "Trackpad"}.get(
            self.state_obj.config.get("mic_button", "master"), "Both")
        self.mic_seg = ctk.CTkSegmentedButton(
            ctrl, values=["Both", "Rumble", "Trackpad"], command=self._apply_mic,
            selected_color=p["accent"], selected_hover_color=p["accent_dark"],
            fg_color=p["sunk"], text_color=p["text"])
        self.mic_seg.set(current)
        self.mic_seg.pack(anchor="w", fill="x", pady=(0, 16))
        ctk.CTkLabel(ctrl, justify="left", text_color=p["muted"], font=ctk.CTkFont(size=12),
                     text="L3 (left stick click)  =  left mouse button\n"
                          "R3 (right stick click)  =  right mouse button\n"
                          "1 finger  =  move    •    tap  =  click\n"
                          "2 fingers  =  scroll    •    2-finger tap  =  right click"
                     ).pack(anchor="w")

    def _grid_knobs(self, parent, section, params, cols):
        p = self.pal
        for i in range(cols):
            parent.grid_columnconfigure(i, weight=1)
        for idx, item in enumerate(params):
            key, label, lo, hi, step = item[0], item[1], item[2], item[3], item[4]
            structural = item[5] if len(item) > 5 else False
            cur = self.state_obj.config[section][key]
            knob = Knob(parent, label, lo, hi, step, cur,
                        command=lambda v, s=section, k=key, rb=structural:
                        self._set(s, k, v, rebuild=rb),
                        face=p["knob_face"], track=p["knob_track"], accent=p["accent"],
                        text=p["knob_text"], edge=p["knob_face"])
            knob.grid(row=idx // cols, column=idx % cols, padx=8, pady=8, sticky="nsew")
            self._knobs[(section, key)] = knob

    def _push_config_to_knobs(self):
        for (section, key), knob in self._knobs.items():
            val = self.state_obj.config[section].get(key)
            if val is not None:
                knob.set(val)

    def _build_profile_bar(self):
        p = self.pal
        self._profile_card = self._card(self)
        self._profile_card.pack(fill="x", padx=16, pady=(8, 16))
        bar = ctk.CTkFrame(self._profile_card, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(bar, text="Profile", text_color=p["text"]).pack(side="left", padx=(0, 8))
        self.profile_menu = ctk.CTkOptionMenu(bar, values=["Default"], command=self._load_profile,
                                              fg_color=p["accent"], button_color=p["accent_dark"],
                                              button_hover_color=p["accent_dark"], width=150)
        self.profile_menu.pack(side="left")
        ctk.CTkButton(bar, text="Save as…", width=80, command=self._save_profile_as,
                      fg_color=p["sunk"], text_color=p["text"], hover_color=p["accent_dark"]
                      ).pack(side="left", padx=6)
        ctk.CTkButton(bar, text="Delete", width=64, command=self._delete_profile,
                      fg_color=p["sunk"], text_color=p["text"], hover_color=p["accent_dark"]
                      ).pack(side="left")
        ctk.CTkButton(bar, text="Save settings", width=110, command=self._save_config,
                      fg_color=p["accent"], hover_color=p["accent_dark"]).pack(side="right")
        self._refresh_profiles()

    def _set(self, section, key, value, rebuild=False):
        self.state_obj.config[section][key] = value
        if rebuild:
            self.state_obj.reload_audio.set()

    def _apply_toggles(self):
        self.state_obj.rumble_enabled = self.rumble_on.get()
        self.state_obj.trackpad_enabled = self.trackpad_on.get()

    def _apply_mic(self, choice):
        self.state_obj.config["mic_button"] = {
            "Both": "master", "Rumble": "rumble", "Trackpad": "trackpad"}[choice]

    def _apply_theme(self, name):
        self.theme_name = name
        self.pal = THEMES[name]
        self.state_obj.config["theme"] = name
        ctk.set_appearance_mode(self.pal["mode"])
        self.attributes("-alpha", self.pal["alpha"])
        self._rebuild()

    def _test_rumble(self):
        ds = self.state_obj.ds
        if ds is None:
            messagebox.showinfo("Test rumble", "Controller not connected.")
            return
        try:
            ds.setLeftMotor(200)
            ds.setRightMotor(160)
            self.after(350, self._safe_motor_off)
        except Exception:
            pass

    def _safe_motor_off(self):
        ds = self.state_obj.ds
        if ds is not None:
            try:
                ds.setLeftMotor(0)
                ds.setRightMotor(0)
            except Exception:
                pass

    def _tick(self):
        st = self.state_obj
        if st.controller_connected:
            self.status_var.set(f"Controller connected    •    battery {st.battery}%")
        else:
            self.status_var.set("Waiting for controller (connect via USB)…")
        self.device_var.set(f"Listening on: {st.listening_on}" if st.listening_on else "")
        self.meter_l.set(st.motor_left / 255)
        self.meter_r.set(st.motor_right / 255)
        self.rumble_on.set(st.rumble_enabled)
        self.trackpad_on.set(st.trackpad_enabled)
        self.after(120, self._tick)

    def _refresh_profiles(self):
        names = sorted(os.path.splitext(f)[0] for f in os.listdir(paths.profiles_dir())
                       if f.endswith(".json"))
        self.profile_menu.configure(values=names or ["Default"])

    def _load_profile(self, name):
        path = os.path.join(paths.profiles_dir(), name + ".json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except OSError:
            return
        self.state_obj.config["rumble"].update(data)
        self.state_obj.reload_audio.set()
        self._push_config_to_knobs()

    def _save_profile_as(self):
        dialog = ctk.CTkInputDialog(text="Profile name:", title="Save profile")
        name = dialog.get_input()
        if not name:
            return
        safe = "".join(c for c in name if c not in '\\/:*?"<>|').strip()
        if not safe:
            return
        with open(os.path.join(paths.profiles_dir(), safe + ".json"), "w", encoding="utf-8") as f:
            json.dump(self.state_obj.config["rumble"], f, indent=2)
        self._refresh_profiles()
        self.profile_menu.set(safe)

    def _delete_profile(self):
        name = self.profile_menu.get()
        if name == "Default":
            messagebox.showinfo("Delete", "The Default profile can't be deleted.")
            return
        if messagebox.askyesno("Delete", f"Delete profile '{name}'?"):
            try:
                os.remove(os.path.join(paths.profiles_dir(), name + ".json"))
            except OSError:
                pass
            self._refresh_profiles()
            self.profile_menu.set("Default")

    def _save_config(self):
        try:
            with open(paths.config_file(), "w", encoding="utf-8") as f:
                json.dump(self.state_obj.config, f, indent=2)
            messagebox.showinfo("Saved", "Settings saved. They'll load automatically next time.")
        except OSError as e:
            messagebox.showerror("Save failed", str(e))

    def _quit(self):
        self.on_quit()
        self.destroy()
