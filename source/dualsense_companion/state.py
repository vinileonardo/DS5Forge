import threading


class AppState:
    """Runtime state shared between the controller engines and the UI."""

    def __init__(self, config):
        self.config = config
        self.rumble_enabled = True
        self.trackpad_enabled = config["trackpad"].get("trackpad_enabled_on_start", True)

        self.controller_connected = False
        self.listening_on = ""
        self.battery = 0
        self.motor_left = 0
        self.motor_right = 0

        self.ds = None
        self.reload_audio = threading.Event()

    def toggle(self, target):
        if target == "rumble":
            self.rumble_enabled = not self.rumble_enabled
        elif target == "trackpad":
            self.trackpad_enabled = not self.trackpad_enabled
        else:  # master: flip both to a single shared state
            new_state = not (self.rumble_enabled or self.trackpad_enabled)
            self.rumble_enabled = new_state
            self.trackpad_enabled = new_state
