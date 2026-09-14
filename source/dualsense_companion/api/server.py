"""Coordinated optional Uvicorn server for the legacy desktop process."""

from __future__ import annotations

import threading
from typing import Any

from ..diagnostics.logging import get_logger

LOGGER = get_logger(__name__)
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def validate_loopback_host(host: str) -> str:
    host = str(host).strip().lower()
    if host not in LOOPBACK_HOSTS:
        raise ValueError("P0 local API may bind only to localhost/loopback addresses")
    return host


def validate_port(port: int) -> int:
    value = int(port)
    if not 1 <= value <= 65_535:
        raise ValueError("API port must be between 1 and 65535")
    return value


class LocalApiServer:
    def __init__(self, facade: Any, *, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.facade = facade
        self.host = validate_loopback_host(host)
        self.port = validate_port(port)
        self._server: Any = None
        self._thread: threading.Thread | None = None

    @property
    def available(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        try:
            import uvicorn  # type: ignore[import-not-found]
        except ImportError:
            LOGGER.warning(
                "API dependencies unavailable; continuing without local server", extra={"event": "api.unavailable"}
            )
            return False
        try:
            from .http import create_app

            app = create_app(self.facade)
        except RuntimeError as exc:
            LOGGER.warning("local API unavailable", extra={"event": "api.unavailable", "error": str(exc)})
            return False
        config = uvicorn.Config(app, host=self.host, port=self.port, log_level="warning", access_log=False)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, name="DS5ForgeApi", daemon=False)
        self._thread.start()
        LOGGER.info("local API starting", extra={"event": "api.start", "path": f"http://{self.host}:{self.port}"})
        return True

    def stop(self, *, join_timeout: float = 5.0) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=join_timeout)
        if self.available:
            LOGGER.error("local API did not stop before timeout", extra={"event": "api.stop_timeout"})
