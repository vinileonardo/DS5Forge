"""Bounded, sanitized Support Bundle generation."""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SENSITIVE_KEY = re.compile(
    r"(token|cookie|password|passwd|secret|credential|authorization|private.?key|api.?key|path|paths|file|directory|cwd|executable)",
    re.I,
)
SENSITIVE_VALUE = re.compile(r"(?i)(bearer\s+|token[=:]\s*|cookie[=:]\s*|password[=:]\s*)\S+")
# Free-text values can still carry absolute machine paths (for example an
# exception string). Windows drive/UNC paths and common POSIX user/system
# directories are redacted even when the key itself is not path-like, so a
# Support Bundle cannot leak the local filesystem layout.
SENSITIVE_PATH = re.compile(
    r"(?i)(?:[A-Za-z]:\\[^\s\"'<>|,;)]+|\\\\[^\s\"'<>|,;)]+|(?<![\w:/])/(?:users|home|root|tmp|var|etc|opt|usr|mnt|media)/[^\s\"'<>|,;)]+)"
)
MAX_ENTRY_BYTES = 64 * 1024
MAX_TOTAL_BYTES = 512 * 1024


def sanitize(value: Any, *, key: str = "") -> Any:
    if SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(name): sanitize(item, key=str(name)) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item, key=key) for item in value]
    if isinstance(value, Path):
        return f"…/{value.name}"
    if isinstance(value, str):
        redacted = SENSITIVE_VALUE.sub("[REDACTED]", value)
        if SENSITIVE_PATH.search(redacted):
            # A free-text value that embeds a machine path is dropped whole so
            # a partial path (for example one containing spaces) cannot leak.
            return "[REDACTED]"
        if key.lower().endswith(("path", "paths", "file", "directory", "cwd", "executable")):
            return f"…/{Path(redacted).name}"
        return redacted[:MAX_ENTRY_BYTES]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:MAX_ENTRY_BYTES]


def build_support_bundle(entries: Mapping[str, Any]) -> bytes:
    output = io.BytesIO()
    readme = b"DS5Forge Support Bundle\nSecrets and sensitive paths are redacted.\n"
    used = len(readme)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in entries.items():
            safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", str(name)).strip("._") or "entry"
            filename = f"{safe_name}.json"
            payload = json.dumps(sanitize(value), ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
            payload = payload[:MAX_ENTRY_BYTES]
            if used + len(payload) > MAX_TOTAL_BYTES:
                break
            archive.writestr(filename, payload)
            used += len(payload)
        archive.writestr("README.txt", readme)
    return output.getvalue()
