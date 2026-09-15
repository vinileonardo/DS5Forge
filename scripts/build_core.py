#!/usr/bin/env python3
"""Build the reproducible, headless PyInstaller core sidecar."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=SOURCE / "dist")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        print("DS5Forge sidecar requires Python 3.12.x", file=sys.stderr)
        return 2
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "build.spec",
        "--distpath",
        str(args.output),
        "--workpath",
        str(SOURCE / "build_tmp"),
        "--noconfirm",
        "--clean",
    ]
    return subprocess.run(command, cwd=SOURCE, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
