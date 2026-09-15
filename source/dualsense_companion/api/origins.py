"""Validated browser origins for the loopback P1 client.

The local API is intentionally not a general CORS service.  These are the
only origins used by the Vite development/preview servers and by Tauri 2's
Windows protocol origin.  Keeping the allow-list here means HTTP and
WebSocket checks cannot drift apart.
"""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit

DEFAULT_ALLOWED_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://tauri.localhost",
)


def validate_origin(origin: str) -> str:
    """Return a supported local origin or raise ``ValueError``.

    Ports are deliberately fixed to Vite's documented dev/preview ports.
    Tauri's origin has no port and is a special, local-only protocol host.
    """

    value = str(origin).strip()
    parsed = urlsplit(value)
    if value == "http://tauri.localhost":
        return value
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("P1 browser origins must be local HTTP origins")
    if parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("P1 browser origins may not contain credentials, paths or query parameters")
    if parsed.port not in {5173, 4173}:
        raise ValueError("P1 browser origins must use Vite development or preview ports")
    return f"http://{parsed.hostname}:{parsed.port}"


def validate_allowed_origins(origins: Iterable[str]) -> tuple[str, ...]:
    """Validate and de-duplicate an origin collection while preserving order."""

    result: list[str] = []
    for origin in origins:
        validated = validate_origin(origin)
        if validated not in result:
            result.append(validated)
    return tuple(result)


def default_allowed_origins() -> tuple[str, ...]:
    """Return a fresh tuple for callers that want the standard P1 policy."""

    return validate_allowed_origins(DEFAULT_ALLOWED_ORIGINS)
