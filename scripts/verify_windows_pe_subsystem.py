#!/usr/bin/env python3
"""Verify Windows executables are built with the expected PE subsystem."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

IMAGE_SUBSYSTEM_WINDOWS_GUI = 2
IMAGE_SUBSYSTEM_WINDOWS_CUI = 3


def read_pe_subsystem(path: Path) -> int:
    data = path.read_bytes()
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ValueError(f"not a PE executable: {path}")

    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_offset + 24 > len(data) or data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise ValueError(f"invalid PE header: {path}")

    optional_header = pe_offset + 24
    if optional_header + 70 > len(data):
        raise ValueError(f"truncated PE optional header: {path}")

    magic = struct.unpack_from("<H", data, optional_header)[0]
    if magic not in (0x10B, 0x20B):
        raise ValueError(f"unsupported PE optional header magic 0x{magic:04x}: {path}")

    return struct.unpack_from("<H", data, optional_header + 68)[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument(
        "--expected",
        choices=("gui", "console"),
        default="gui",
        help="Expected Windows subsystem for every executable (default: gui)",
    )
    args = parser.parse_args()

    expected = IMAGE_SUBSYSTEM_WINDOWS_GUI if args.expected == "gui" else IMAGE_SUBSYSTEM_WINDOWS_CUI
    failures: list[str] = []
    for path in args.paths:
        try:
            actual = read_pe_subsystem(path)
        except (OSError, ValueError) as exc:
            failures.append(str(exc))
            continue
        if actual != expected:
            failures.append(f"{path}: expected subsystem {expected}, got {actual}")
        else:
            print(f"{path}: Windows subsystem OK ({args.expected})")

    if failures:
        for failure in failures:
            print(failure)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
