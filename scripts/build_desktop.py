#!/usr/bin/env python3
"""Build the SPA and (when a sidecar is present) the Tauri desktop target."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tauri", action="store_true", help="also invoke the native Tauri build")
    args = parser.parse_args()
    commands = [["npm", "run", "build"]]
    if args.tauri:
        commands.append(["npm", "run", "tauri:build"])
    for command in commands:
        result = subprocess.run(command, cwd=ROOT / "frontend", check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
