#!/usr/bin/env python3
"""Build the Windows NSIS installer and signed updater artifacts on release."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args()
    if args.release and not os.environ.get("TAURI_SIGNING_PRIVATE_KEY"):
        print(
            "Release installer build requires TAURI_SIGNING_PRIVATE_KEY; no key is stored in the repository.",
            file=sys.stderr,
        )
        return 2
    if args.release and not os.environ.get("TAURI_SIGNING_PUBLIC_KEY"):
        print(
            "Release installer build requires TAURI_SIGNING_PUBLIC_KEY; no key is stored in the repository.",
            file=sys.stderr,
        )
        return 2
    config_path: Path | None = None
    try:
        command = ["npm", "run", "tauri:build", "--"]
        if args.release:
            fd, raw_path = tempfile.mkstemp(prefix="ds5forge-tauri-release-", suffix=".json")
            os.close(fd)
            config_path = Path(raw_path)
            overlay = {
                "bundle": {"createUpdaterArtifacts": True},
                "plugins": {
                    "updater": {
                        "pubkey": os.environ["TAURI_SIGNING_PUBLIC_KEY"],
                        "endpoints": ["https://github.com/vinileonardo/DS5Forge/releases/latest/download/latest.json"],
                    }
                },
            }
            config_path.write_text(json.dumps(overlay), encoding="utf-8")
            command.extend(["--config", str(config_path)])
        return subprocess.run(command, cwd=ROOT / "frontend", check=False).returncode
    finally:
        if config_path is not None:
            config_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
