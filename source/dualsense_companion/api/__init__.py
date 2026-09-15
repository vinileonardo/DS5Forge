"""Versioned local HTTP and WebSocket API with lazy web dependencies."""

from typing import Any

from .origins import DEFAULT_ALLOWED_ORIGINS, validate_allowed_origins, validate_origin

API_PREFIX = "/api/v1"


def create_app(*args: Any, **kwargs: Any) -> Any:
    from .http import create_app as _create_app

    return _create_app(*args, **kwargs)


__all__ = [
    "API_PREFIX",
    "DEFAULT_ALLOWED_ORIGINS",
    "create_app",
    "validate_allowed_origins",
    "validate_origin",
]
