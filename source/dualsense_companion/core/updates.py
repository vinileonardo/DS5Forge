"""Signed-release metadata validation shared by diagnostics and tests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

SEMVER_RE = re.compile(r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


def version_tuple(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not SEMVER_RE.fullmatch(value):
        raise ValueError("version must be SemVer X.Y.Z")
    numbers = value.lstrip("v").split("-", 1)[0].split("+", 1)[0].split(".")
    return tuple(int(item) for item in numbers)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class UpdateMetadata:
    version: str
    notes: str
    pub_date: str | None
    signature: str
    installer_url: str
    target: str = "windows-x86_64"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> UpdateMetadata:
        allowed = {"version", "notes", "pub_date", "signature", "installer_url", "target"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError("update metadata contains unknown fields")
        version = payload.get("version")
        if not isinstance(version, str):
            raise ValueError("update metadata requires a string version")
        version_tuple(version)
        notes = payload.get("notes", "")
        if not isinstance(notes, str):
            raise ValueError("update metadata notes must be a string")
        pub_date = payload.get("pub_date")
        if pub_date is not None and not isinstance(pub_date, str):
            raise ValueError("update metadata pub_date must be a string")
        signature = payload.get("signature")
        url = payload.get("installer_url")
        if not isinstance(signature, str) or not signature.strip() or len(signature) > 16_384:
            raise ValueError("update metadata requires a detached signature")
        if not isinstance(url, str) or len(url) > 2_048:
            raise ValueError("update installer URL must use HTTPS")
        parsed_url = urlsplit(url)
        try:
            _ = parsed_url.port
        except ValueError as exc:
            raise ValueError("update installer URL contains an invalid port") from exc
        if (
            parsed_url.scheme != "https"
            or not parsed_url.hostname
            or parsed_url.username
            or parsed_url.password
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ValueError("update installer URL must be an HTTPS URL without credentials or query data")
        target = payload.get("target", "windows-x86_64")
        if not isinstance(target, str) or target != "windows-x86_64":
            raise ValueError("update metadata target must be windows-x86_64")
        return cls(
            version,
            notes[:8_192],
            pub_date,
            signature,
            url,
            target,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "notes": self.notes,
            "pub_date": self.pub_date,
            "signature": self.signature,
            "installer_url": self.installer_url,
            "target": self.target,
        }


def evaluate_update(current_version: str, metadata: UpdateMetadata) -> dict[str, Any]:
    current = version_tuple(current_version)
    candidate = version_tuple(metadata.version)
    if candidate < current:
        return {"available": False, "status": "rejected_downgrade", "version": metadata.version}
    if candidate == current:
        return {"available": False, "status": "up_to_date", "version": metadata.version}
    return {"available": True, "status": "available", "version": metadata.version, "notes": metadata.notes}
