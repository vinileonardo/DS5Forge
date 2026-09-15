#!/usr/bin/env python3
"""Generate stable SHA-256 checksums for release artifacts."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    output = (args.output or args.directory / "SHA256SUMS.txt").resolve()
    files = sorted(
        path
        for path in args.directory.rglob("*")
        if path.is_file() and not path.name.endswith(".sha256") and path.resolve() != output
    )
    lines = []
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(args.directory).as_posix()}")
    output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
