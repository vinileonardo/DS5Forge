"""Application entry point: load config, start the controller manager, open the UI."""

import json

from . import paths
from .controller import ControllerManager
from .gui import ControlPanel
from .state import AppState


def load_config():
    paths.ensure_seeded()
    with open(paths.config_file(), "r", encoding="utf-8-sig") as f:
        return json.load(f)


def main():
    config = load_config()
    state = AppState(config)

    manager = ControllerManager(state)
    manager.start()

    ui = ControlPanel(state, on_quit=manager.stop)
    ui.mainloop()


if __name__ == "__main__":
    main()
