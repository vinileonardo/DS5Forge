#!/usr/bin/env python3
"""Create static Tauri updater metadata without publishing a release."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=(ROOT / "VERSION").read_text(encoding="utf-8").strip())
    parser.add_argument("--signature", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--notes", default="")
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "latest.json")
    args = parser.parse_args()
    if not SEMVER.fullmatch(args.version):
        raise SystemExit("release metadata version must be SemVer X.Y.Z")
    signature = args.signature.strip()
    if not signature:
        raise SystemExit("release metadata requires a detached signature")
    if len(args.url) > 2_048:
        raise SystemExit("release metadata URL is too long")
    parsed_url = urlsplit(args.url)
    try:
        _ = parsed_url.port
    except ValueError as exc:
        raise SystemExit("release metadata URL contains an invalid port") from exc
    if (
        parsed_url.scheme != "https"
        or not parsed_url.hostname
        or parsed_url.username
        or parsed_url.password
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise SystemExit("release metadata URL must use HTTPS")
    payload = {
        "version": args.version,
        "notes": args.notes[:8192],
        "pub_date": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "platforms": {
            "windows-x86_64": {"signature": signature, "url": args.url},
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
