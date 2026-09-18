#!/usr/bin/env python3
"""Fetch the pinned HIDMaestro SDK used by the Exclusive helper build.

This is a build-time dependency only. The downloaded archive and extracted DLL
are ignored by git; release builds must verify the published v1.8.0 archive
before compiling DS5ForgeExclusiveHelper.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "exclusive-helper" / "vendor"
HIDMAESTRO_VERSION = "1.8.0"
HIDMAESTRO_URL = (
    "https://github.com/hifihedgehog/HIDMaestro/releases/download/"
    f"v{HIDMAESTRO_VERSION}/HIDMaestro-v{HIDMAESTRO_VERSION}.zip"
)
HIDMAESTRO_ZIP_SHA256 = "1e5f5019c20e4be8f922c7aa5a86ee87eb01f7aa851fe38daea14d0ce4fd8240"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_member(archive: zipfile.ZipFile, basename: str) -> str:
    matches = [name for name in archive.namelist() if Path(name).name.casefold() == basename.casefold()]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one {basename!r} in HIDMaestro archive, found {len(matches)}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    dll = VENDOR / "HIDMaestro.Core.dll"
    license_path = VENDOR / "HIDMaestro.LICENSE"
    if dll.is_file() and license_path.is_file() and not args.force:
        print(f"HIDMaestro SDK already prepared: {dll}")
        return 0

    VENDOR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ds5forge-hidmaestro-") as temporary:
        archive_path = Path(temporary) / f"HIDMaestro-v{HIDMAESTRO_VERSION}.zip"
        request = urllib.request.Request(HIDMAESTRO_URL, headers={"User-Agent": "DS5Forge-build/0.4"})
        with urllib.request.urlopen(request, timeout=60) as response, archive_path.open("wb") as output:
            shutil.copyfileobj(response, output)
        actual = sha256(archive_path)
        if actual.lower() != HIDMAESTRO_ZIP_SHA256:
            raise RuntimeError(
                "HIDMaestro archive integrity check failed: "
                f"expected {HIDMAESTRO_ZIP_SHA256}, got {actual}"
            )
        with zipfile.ZipFile(archive_path) as archive:
            dll_member = find_member(archive, "HIDMaestro.Core.dll")
            license_member = find_member(archive, "LICENSE")
            dll.write_bytes(archive.read(dll_member))
            license_path.write_bytes(archive.read(license_member))

    print(f"prepared HIDMaestro v{HIDMAESTRO_VERSION}: {dll}")
    print(f"sdk sha256: {sha256(dll)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
