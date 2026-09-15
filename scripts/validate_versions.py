#!/usr/bin/env python3
"""Validate that all release-facing version consumers match VERSION."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_declared_version(path: Path, pattern: str) -> str:
    """Return the captured version or fail closed on a malformed manifest."""

    match = re.search(pattern, path.read_text(encoding="utf-8"), re.M)
    if match is None:
        raise SystemExit(f"{path.relative_to(ROOT)}: no version declaration matched {pattern!r}")
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", help="expected release version or v-prefixed tag")
    args = parser.parse_args()
    expected_arg = args.expected
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not SEMVER.fullmatch(version):
        print(f"Invalid VERSION: {version}", file=sys.stderr)
        return 1
    expected = expected_arg.removeprefix("v") if expected_arg else None
    if expected is not None and version != expected:
        print(f"VERSION {version} does not match expected release tag {expected_arg}", file=sys.stderr)
        return 1
    checks = {
        "pyproject.toml": read_declared_version(ROOT / "pyproject.toml", r'^version\s*=\s*"([^"]+)"'),
        "frontend/package.json": read_json(ROOT / "frontend/package.json")["version"],
        "frontend/package-lock.json": read_json(ROOT / "frontend/package-lock.json")["version"],
        "frontend/src-tauri/tauri.conf.json": read_json(ROOT / "frontend/src-tauri/tauri.conf.json")["version"],
        "frontend/src-tauri/Cargo.toml": read_declared_version(
            ROOT / "frontend/src-tauri/Cargo.toml", r'^version\s*=\s*"([^"]+)"'
        ),
        "source/dualsense_companion/version.py": read_declared_version(
            ROOT / "source/dualsense_companion/version.py", r'^FALLBACK_VERSION\s*=\s*"([^"]+)"'
        ),
    }
    mismatches = {name: value for name, value in checks.items() if value != version}
    if mismatches:
        for name, value in mismatches.items():
            print(f"{name}: {value} != {version}", file=sys.stderr)
        return 1
    print(f"DS5Forge version OK: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
