"""Convert system audio into DualSense rumble via WASAPI loopback."""

import math
import threading
import time

import numpy as np
import pyaudiowpatch as pyaudio


class Biquad:
    def __init__(self, b0, b1, b2, a1, a2):
        self.b0, self.b1, self.b2 = b0, b1, b2
        self.a1, self.a2 = a1, a2
        self.x1 = self.x2 = self.y1 = self.y2 = 0.0

    @classmethod
    def lowpass(cls, fs, fc, q=0.707):
        w0 = 2 * math.pi * fc / fs
        alpha = math.sin(w0) / (2 * q)
        cosw = math.cos(w0)
        a0 = 1 + alpha
        return cls((1 - cosw) / 2 / a0, (1 - cosw) / a0, (1 - cosw) / 2 / a0,
                   (-2 * cosw) / a0, (1 - alpha) / a0)

    @classmethod
    def bandpass(cls, fs, fc, q=0.9):
        w0 = 2 * math.pi * fc / fs
        alpha = math.sin(w0) / (2 * q)
        cosw = math.cos(w0)
        a0 = 1 + alpha
        return cls(alpha / a0, 0.0, -alpha / a0,
                   (-2 * cosw) / a0, (1 - alpha) / a0)

    def process(self, x):
        y = np.empty_like(x)
        x1, x2, y1, y2 = self.x1, self.x2, self.y1, self.y2
        b0, b1, b2, a1, a2 = self.b0, self.b1, self.b2, self.a1, self.a2
        for i in range(len(x)):
            xi = x[i]
            yi = b0 * xi + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
            x2, x1 = x1, xi
            y2, y1 = y1, yi
            y[i] = yi
        self.x1, self.x2, self.y1, self.y2 = x1, x2, y1, y2
        return y


class EnvelopeFollower:
    def __init__(self, attack_ms, release_ms, chunk_ms):
        self.attack = math.exp(-chunk_ms / max(attack_ms, 1e-3))
        self.release = math.exp(-chunk_ms / max(release_ms, 1e-3))
        self.value = 0.0

    def update(self, peak):
        coef = self.attack if peak > self.value else self.release
        self.value = coef * self.value + (1 - coef) * peak
        return self.value


class AudioRumbleEngine(threading.Thread):
    CHUNK_MS = 10

    def __init__(self, state):
        super().__init__(daemon=True, name="AudioRumble")
        self.state = state
        self.stop_flag = threading.Event()
        self.last_left = -1
        self.last_right = -1
        self.status = "starting"

    @property
    def cfg(self):
        return self.state.config["rumble"]

    def _open_loopback(self, p):
        wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_out = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
        loopback = None
        if not default_out.get("isLoopbackDevice"):
            for dev in p.get_loopback_device_info_generator():
                if default_out["name"] in dev["name"]:
                    loopback = dev
                    break
        loopback = loopback or default_out
        rate = int(loopback["defaultSampleRate"])
        channels = max(1, int(loopback["maxInputChannels"]))
        frames = max(64, int(rate * self.CHUNK_MS / 1000))
        stream = p.open(format=pyaudio.paFloat32, channels=channels, rate=rate,
                        input=True, input_device_index=loopback["index"],
                        frames_per_buffer=frames)
        return stream, rate, channels, frames, loopback["name"]

    def _map(self, level, transient, c, texture=False):
        # Upward expander: silence below the gate, gamma>1 curve up to the
        # impact level, plus an onset term that only counts once the sound is
        # loud enough to be a real hit (keeps footsteps from rumbling).
        gate = c["gate"] * (c["texture_gate_mult"] if texture else 1.0)
        span = max(c["impact_level"] - gate, 1e-6)
        x = min(1.0, max(0.0, (level - gate) / span)) ** c["gamma"]
        t = 0.0
        if level >= c["transient_min_level"] and transient > 0:
            t = min(1.0, (transient * c["transient_gain"]) / max(c["impact_level"], 1e-6))
        drive = min(1.0, x + c["transient_weight"] * t)
        if drive < c["drive_gate"]:
            return 0
        floor = 0 if texture else c["min_rumble"]
        return int(round(floor + drive * (c["max_rumble"] - floor)))

    def run(self):
        while not self.stop_flag.is_set():
            try:
                self._run_once()
            except Exception as e:
                self.status = f"audio error ({e}); retrying"
                self._set_motors(0, 0)
                time.sleep(2)

    def _run_once(self):
        with pyaudio.PyAudio() as p:
            wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_idx = wasapi["defaultOutputDevice"]
            stream, rate, channels, frames, name = self._open_loopback(p)
            self.status = f"listening on: {name}"
            self.state.listening_on = name
            last_dev_check = time.monotonic()

            c = self.cfg
            lp = Biquad.lowpass(rate, c["heavy_cutoff_hz"])
            bp = Biquad.bandpass(rate, c["texture_center_hz"])
            fast_l = EnvelopeFollower(c["fast_attack_ms"], c["fast_release_ms"], self.CHUNK_MS)
            base_l = EnvelopeFollower(c["baseline_attack_ms"], c["baseline_release_ms"], self.CHUNK_MS)
            fast_r = EnvelopeFollower(c["fast_attack_ms"], c["fast_release_ms"] * 0.7, self.CHUNK_MS)

            while not self.stop_flag.is_set():
                now = time.monotonic()
                if now - last_dev_check > 2.0:
                    last_dev_check = now
                    with pyaudio.PyAudio() as p2:
                        w2 = p2.get_host_api_info_by_type(pyaudio.paWASAPI)
                        if w2["defaultOutputDevice"] != default_idx:
                            break
                # Filter/envelope settings changed in the UI -> rebuild.
                if self.state.reload_audio.is_set():
                    self.state.reload_audio.clear()
                    break

                data = stream.read(frames, exception_on_overflow=False)
                if not self.state.rumble_enabled:
                    self._set_motors(0, 0)
                    continue

                samples = np.frombuffer(data, dtype=np.float32)
                if channels > 1:
                    samples = samples.reshape(-1, channels).mean(axis=1)

                low = lp.process(samples)
                mid = bp.process(samples)
                peak_low = float(np.max(np.abs(low))) if len(low) else 0.0
                peak_mid = float(np.max(np.abs(mid))) if len(mid) else 0.0

                elf = fast_l.update(peak_low)
                elb = base_l.update(peak_low)
                transient = max(0.0, elf - elb)
                erf = fast_r.update(peak_mid)

                left = self._map(elf, transient, c, texture=False)
                right = self._map(erf, transient * 0.5, c, texture=True)
                self._set_motors(left, right)

            stream.stop_stream()
            stream.close()
        self._set_motors(0, 0)

    def _set_motors(self, left, right):
        self.state.motor_left = left
        self.state.motor_right = right
        if abs(left - self.last_left) < 3 and abs(right - self.last_right) < 3:
            if not (left == 0 and right == 0 and (self.last_left or self.last_right)):
                return
        self.last_left, self.last_right = left, right
        ds = self.state.ds
        if ds is None:
            return
        try:
            ds.setLeftMotor(left)
            ds.setRightMotor(right)
        except Exception:
            pass

    def stop(self):
        self.stop_flag.set()
