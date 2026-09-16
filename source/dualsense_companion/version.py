"""Canonical DS5Forge version lookup.

The repository-level ``VERSION`` file is the release source of truth.  Frozen
builds may not have the checkout beside the package, so a deterministic
fallback keeps the runtime contract available while the release validator
still checks every checked-in consumer.
"""

from __future__ import annotations

import os
from pathlib import Path

FALLBACK_VERSION = "0.4.0-rc.7"


def read_version() -> str:
    override = os.environ.get("DS5FORGE_VERSION", "").strip()
    if override:
        return override
    candidates = (
        Path(__file__).resolve().parents[2] / "VERSION",
        Path.cwd() / "VERSION",
    )
    for candidate in candidates:
        try:
            value = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value
    return FALLBACK_VERSION


__version__ = read_version()
