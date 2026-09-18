#!/usr/bin/env python3
"""Build the pinned, self-contained Windows Exclusive helper."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "exclusive-helper" / "DS5ForgeExclusiveHelper.csproj"
DEFAULT_OUTPUT = ROOT / "exclusive-helper" / "dist"
PREPARE = ROOT / "scripts" / "prepare_hidmaestro_sdk.py"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dotnet_has_net10(dotnet: str) -> bool:
    completed = subprocess.run(
        [dotnet, "--list-sdks"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return False
    return any(line.lstrip().startswith("10.") for line in completed.stdout.splitlines())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--configuration", default="Release")
    parser.add_argument("--dotnet", default=None)
    args = parser.parse_args()

    dotnet = args.dotnet or shutil.which("dotnet")
    if not dotnet:
        print(".NET SDK was not found. DS5Forge Exclusive helper requires .NET 10 SDK to build.", file=sys.stderr)
        return 2
    if not dotnet_has_net10(dotnet):
        print(
            ".NET 10 SDK is not installed in this build environment. "
            "No system changes were attempted.",
            file=sys.stderr,
        )
        return 2

    prepared = subprocess.run([sys.executable, str(PREPARE)], cwd=ROOT, check=False)
    if prepared.returncode != 0:
        return prepared.returncode

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    command = [
        dotnet,
        "publish",
        str(PROJECT),
        "--configuration",
        args.configuration,
        "--runtime",
        "win-x64",
        "--self-contained",
        "true",
        "--output",
        str(output),
        "--nologo",
    ]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        return completed.returncode

    helper = output / "DS5ForgeExclusiveHelper.exe"
    if not helper.is_file():
        print(f"Exclusive helper build did not produce {helper}", file=sys.stderr)
        return 1
    print(f"built {helper}")
    print(f"sha256 {sha256(helper)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
