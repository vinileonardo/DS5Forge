#!/usr/bin/env python3
"""Publish a signed DS5Forge tag and refresh the prerelease update channel."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path

SEMVER_TAG = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
RC_CHANNEL_TAG = "update-rc"


def is_prerelease(tag: str) -> bool:
    """Return whether a validated v-prefixed SemVer tag is a prerelease."""

    if not SEMVER_TAG.fullmatch(tag):
        raise ValueError(f"invalid release tag: {tag}")
    return "-" in tag.split("+", 1)[0]


def run_gh(args: list[str], *, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run GitHub CLI without ever putting credentials on the command line."""

    if not os.environ.get("GH_TOKEN"):
        raise RuntimeError("GH_TOKEN is required for release publication")
    result = subprocess.run(
        ["gh", *args],
        check=False,
        text=True,
        capture_output=capture,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() if capture else ""
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"gh {' '.join(args[:3])} failed with exit code {result.returncode}{suffix}")
    return result


def release_exists(tag: str, repo: str) -> bool:
    result = run_gh(["release", "view", tag, "--repo", repo], capture=True, check=False)
    return result.returncode == 0


def release_assets(bundle_dir: Path, core_path: Path) -> list[Path]:
    installers = sorted(bundle_dir.glob("*-setup.exe"))
    if len(installers) != 1:
        raise RuntimeError(f"expected exactly one NSIS installer, found {len(installers)}")
    installer = installers[0]
    assets = [
        installer,
        Path(f"{installer}.sig"),
        bundle_dir / "latest.json",
        bundle_dir / "SHA256SUMS.txt",
        core_path,
    ]
    missing = [str(path) for path in assets if not path.is_file()]
    if missing:
        raise RuntimeError(f"release assets missing: {', '.join(missing)}")
    return assets


def publish_versioned_release(tag: str, repo: str, assets: list[Path]) -> None:
    prerelease = is_prerelease(tag)
    asset_args = [str(path.resolve()) for path in assets]
    if release_exists(tag, repo):
        for asset in asset_args:
            run_gh(["release", "upload", tag, asset, "--repo", repo, "--clobber"])
        edit_args = ["release", "edit", tag, "--repo", repo]
        edit_args.append("--prerelease" if prerelease else "--latest")
        run_gh(edit_args)
        return

    args = [
        "release",
        "create",
        tag,
        *asset_args,
        "--repo",
        repo,
        "--verify-tag",
        "--title",
        f"DS5Forge {tag}",
        "--generate-notes",
    ]
    if prerelease:
        args.extend(["--prerelease", "--latest=false"])
    else:
        args.append("--latest")
    run_gh(args)


def refresh_rc_channel(repo: str, metadata_path: Path) -> None:
    metadata = str(metadata_path.resolve())
    if release_exists(RC_CHANNEL_TAG, repo):
        run_gh(["release", "upload", RC_CHANNEL_TAG, metadata, "--repo", repo, "--clobber"])
        return
    run_gh(
        [
            "release",
            "create",
            RC_CHANNEL_TAG,
            metadata,
            "--repo",
            repo,
            "--target",
            "main",
            "--title",
            "DS5Forge RC update channel",
            "--notes",
            "Machine-managed updater metadata for prerelease installations. Do not install this tag directly.",
            "--prerelease",
            "--latest=false",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--core", type=Path, required=True)
    args = parser.parse_args()

    if not SEMVER_TAG.fullmatch(args.tag):
        raise SystemExit("release tag must be v-prefixed SemVer")
    assets = release_assets(args.bundle_dir, args.core)
    publish_versioned_release(args.tag, args.repo, assets)
    refresh_rc_channel(args.repo, args.bundle_dir / "latest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
