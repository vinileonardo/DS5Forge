"""Owns the controller connection and keeps the engines running across reconnects."""

import threading
import time

from pydualsense import pydualsense

from .audio_rumble import AudioRumbleEngine
from .touch_mouse import TouchMouseEngine


class ControllerManager(threading.Thread):
    def __init__(self, state):
        super().__init__(daemon=True, name="ControllerManager")
        self.state = state
        self.stop_flag = threading.Event()
        self.status = "waiting for controller"

    def run(self):
        while not self.stop_flag.is_set():
            ds = self._connect()
            if ds is None:
                return

            self.state.ds = ds
            self.state.controller_connected = True
            self._startup_feedback(ds)

            rumble = AudioRumbleEngine(self.state)
            touch = TouchMouseEngine(self.state)
            rumble.start()
            touch.start()
            self.status = "connected"

            while not self.stop_flag.is_set() and ds.connected:
                self.state.battery = getattr(ds.battery, "Level", 0)
                time.sleep(1)

            rumble.stop()
            touch.stop()
            self.state.controller_connected = False
            self.state.ds = None
            try:
                ds.setLeftMotor(0)
                ds.setRightMotor(0)
                ds.close()
            except Exception:
                pass

            if self.stop_flag.is_set():
                return
            self.status = "controller lost — reconnecting"
            time.sleep(2)

    def _connect(self):
        while not self.stop_flag.is_set():
            try:
                ds = pydualsense()
                ds.init()
                return ds
            except Exception:
                self.status = "waiting for controller"
                time.sleep(2)
        return None

    def _startup_feedback(self, ds):
        try:
            ds.light.setColorI(0, 80, 255)
            for _ in range(2):
                ds.setLeftMotor(100)
                time.sleep(0.15)
                ds.setLeftMotor(0)
                time.sleep(0.1)
        except Exception:
            pass

    def stop(self):
        self.stop_flag.set()
