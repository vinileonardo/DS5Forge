"""Application composition: one facade, optional API server and legacy GUI."""

from __future__ import annotations

import argparse
import threading
from collections.abc import Sequence
from typing import Any

from .core.config import ConfigRepository
from .core.facade import CoreFacade
from .diagnostics.logging import configure_logging, get_logger

LOGGER = get_logger(__name__)


def load_config() -> dict:
    """Compatibility helper for the upstream launcher and integrations."""

    return ConfigRepository.default().load()


class ApplicationRuntime:
    def __init__(
        self,
        facade: CoreFacade | None = None,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        start_api: bool = True,
    ) -> None:
        self.start_api = start_api
        if self.start_api:
            from .api.server import validate_loopback_host, validate_port

            self.host = validate_loopback_host(host)
            self.port = validate_port(port)
        else:
            self.host = str(host)
            self.port = int(port)
        if facade is None:
            from .platform.windows.composition import create_windows_facade

            facade = create_windows_facade()
        self.facade = facade
        self.api_server: Any = None
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self.facade.start()
        if self.start_api:
            from .api.server import LocalApiServer

            self.api_server = LocalApiServer(self.facade, host=self.host, port=self.port)
            self.api_server.start()
        self._started = True

    def stop(self) -> None:
        if self.api_server is not None:
            self.api_server.stop()
        self.facade.stop()
        self._started = False


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="DS5Forge wired DualSense companion")
    parser.add_argument("--headless", action="store_true", help="run the core/API without the legacy GUI")
    parser.add_argument("--no-api", action="store_true", help="do not start the local API server")
    parser.add_argument("--host", default="127.0.0.1", help="API bind address (loopback only in P0)")
    parser.add_argument("--port", type=int, default=8765, help="API port")
    args = parser.parse_args(argv)
    configure_logging()
    runtime = ApplicationRuntime(host=args.host, port=args.port, start_api=not args.no_api)
    runtime.start()
    try:
        if args.headless:
            stop_event = threading.Event()
            stop_event.wait()
        else:
            # Keep customtkinter optional for headless/CI use and ensure it is
            # never an authority for controller state.
            from .gui import ControlPanel

            ui = ControlPanel(runtime.facade, on_quit=runtime.stop)
            ui.mainloop()
    except KeyboardInterrupt:
        LOGGER.info("interrupt received", extra={"event": "app.interrupt"})
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
