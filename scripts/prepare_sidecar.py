#!/usr/bin/env python3
"""Place a built sidecar at the target-triple path required by Tauri."""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def target_triple() -> str:
    try:
        output = subprocess.check_output(["rustc", "-vV"], text=True, stderr=subprocess.DEVNULL)
        for line in output.splitlines():
            if line.startswith("host:"):
                return line.split(":", 1)[1].strip()
    except (OSError, subprocess.CalledProcessError):
        pass
    if sys.platform == "win32":
        return (
            "x86_64-pc-windows-msvc" if platform.machine().lower() in {"amd64", "x86_64"} else "aarch64-pc-windows-msvc"
        )
    return "x86_64-unknown-linux-gnu"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT / "source" / "dist" / "DS5ForgeCore.exe")
    parser.add_argument("--target", default=None)
    parser.add_argument("--optional", action="store_true")
    args = parser.parse_args()
    source = args.source
    if not source.exists():
        if args.optional:
            print(f"sidecar not found; Tauri build will require it: {source}")
            return 0
        print(f"sidecar not found: {source}", file=sys.stderr)
        return 1
    target = args.target or target_triple()
    destination_dir = ROOT / "frontend" / "src-tauri" / "binaries"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"ds5forge-core-{target}{source.suffix}"
    shutil.copy2(source, destination)
    print(f"prepared {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
