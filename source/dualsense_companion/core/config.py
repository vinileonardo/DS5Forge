"""Versioned configuration and profile repository.

The repository keeps bundled defaults read-only and writes only to the user
directory. A malformed user file falls back to the known-good bundled schema;
the caller can surface the structured error through diagnostics/health.
"""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .. import paths
from ..diagnostics.logging import get_logger
from ..domain.errors import ConfigValidationError, DS5ForgeError, ErrorCode
from ..domain.models import finite_number

LOGGER = get_logger(__name__)
SCHEMA_VERSION = 1
PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}$")

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "theme": "Light",
    "mic_button": "master",
    "rumble": {
        "heavy_cutoff_hz": 150,
        "texture_center_hz": 300,
        "fast_attack_ms": 5,
        "fast_release_ms": 110,
        "baseline_attack_ms": 350,
        "baseline_release_ms": 1800,
        "gate": 0.05,
        "impact_level": 0.55,
        "gamma": 2.2,
        "transient_min_level": 0.22,
        "transient_gain": 3.0,
        "transient_weight": 0.6,
        "drive_gate": 0.06,
        "texture_gate_mult": 1.4,
        "min_rumble": 28,
        "max_rumble": 255,
    },
    "trackpad": {
        "trackpad_enabled_on_start": True,
        "pointer_speed": 0.75,
        "acceleration": 0.006,
        "accel_cap": 1.2,
        "scroll_speed": 0.35,
        "tap_to_click": True,
    },
}

RUMBLE_RANGES: dict[str, tuple[float, float]] = {
    "heavy_cutoff_hz": (1, 20_000),
    "texture_center_hz": (1, 20_000),
    "fast_attack_ms": (0.1, 10_000),
    "fast_release_ms": (0.1, 10_000),
    "baseline_attack_ms": (0.1, 10_000),
    "baseline_release_ms": (0.1, 20_000),
    "gate": (0, 1),
    "impact_level": (0.001, 1),
    "gamma": (0.01, 10),
    "transient_min_level": (0, 1),
    "transient_gain": (0, 20),
    "transient_weight": (0, 1),
    "drive_gate": (0, 1),
    "texture_gate_mult": (0, 10),
    "min_rumble": (0, 255),
    "max_rumble": (0, 255),
}

TRACKPAD_RANGES: dict[str, tuple[float, float]] = {
    "pointer_speed": (0.01, 10),
    "acceleration": (0, 1),
    "accel_cap": (0, 10),
    "scroll_speed": (0.01, 10),
}


class ProfileNotFoundError(DS5ForgeError):
    def __init__(self, name: str) -> None:
        super().__init__(ErrorCode.PROFILE_NOT_FOUND, f"Profile '{name}' was not found.", fields={"name": name})


def default_config() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_CONFIG)


def merge_config(base: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(base))
    for key, value in patch.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = merge_config(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def validate_config(config: Mapping[str, Any], *, allow_partial: bool = False) -> dict[str, Any]:
    if not isinstance(config, Mapping):
        raise ConfigValidationError(fields={"config": "must be an object"})
    allowed = {"schema_version", "theme", "mic_button", "rumble", "trackpad"}
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise ConfigValidationError(fields={"unknown": unknown})

    candidate = copy.deepcopy(dict(config)) if allow_partial else merge_config(DEFAULT_CONFIG, config)
    if not allow_partial:
        version = candidate.get("schema_version", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise ConfigValidationError(fields={"schema_version": f"expected {SCHEMA_VERSION}"})
        if candidate.get("theme") not in {"Light", "Dark", "Liquid Glass"}:
            raise ConfigValidationError(fields={"theme": "unsupported theme"})
        if candidate.get("mic_button") not in {"master", "rumble", "trackpad"}:
            raise ConfigValidationError(fields={"mic_button": "must be master, rumble or trackpad"})
        _validate_section(candidate["rumble"], RUMBLE_RANGES, "rumble")
        _validate_section(candidate["trackpad"], TRACKPAD_RANGES, "trackpad")
        _validate_bool(candidate["trackpad"], "trackpad_enabled_on_start", "trackpad")
        _validate_bool(candidate["trackpad"], "tap_to_click", "trackpad")
        if candidate["rumble"]["min_rumble"] > candidate["rumble"]["max_rumble"]:
            raise ConfigValidationError(fields={"rumble.min_rumble": "must not exceed max_rumble"})
        return candidate

    return validate_config(merge_config(DEFAULT_CONFIG, candidate))


def validate_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(profile, Mapping):
        raise ConfigValidationError("Profile is invalid.", fields={"profile": "must be an object"})
    payload = profile.get("rumble", profile)
    if not isinstance(payload, Mapping):
        raise ConfigValidationError("Profile is invalid.", fields={"rumble": "must be an object"})
    try:
        normalized = validate_config({"rumble": payload})["rumble"]
    except ConfigValidationError as exc:
        raise ConfigValidationError("Profile is invalid.", fields=exc.fields, detail=exc.detail) from exc
    return normalized


def _validate_section(section: Any, ranges: Mapping[str, tuple[float, float]], prefix: str) -> None:
    if not isinstance(section, Mapping):
        raise ConfigValidationError(fields={prefix: "must be an object"})
    unknown = sorted(
        set(section) - set(ranges) - ({"trackpad_enabled_on_start", "tap_to_click"} if prefix == "trackpad" else set())
    )
    if unknown:
        raise ConfigValidationError(fields={prefix: {"unknown": unknown}})
    for key, (minimum, maximum) in ranges.items():
        value: Any = section.get(key)
        if not finite_number(value) or not minimum <= float(value) <= maximum:
            raise ConfigValidationError(fields={f"{prefix}.{key}": f"must be between {minimum} and {maximum}"})


def _validate_bool(section: Mapping[str, Any], key: str, prefix: str) -> None:
    if not isinstance(section.get(key), bool):
        raise ConfigValidationError(fields={f"{prefix}.{key}": "must be boolean"})


class ConfigRepository:
    """Atomic config/profile persistence with bundled/user separation."""

    def __init__(
        self,
        *,
        config_path: Path,
        bundled_config_path: Path | None = None,
        bundled_profiles_dir: Path | None = None,
        user_profiles_dir: Path | None = None,
    ) -> None:
        self.config_path = Path(config_path)
        self.bundled_config_path = bundled_config_path
        self.bundled_profiles_dir = bundled_profiles_dir
        self.user_profiles_dir = user_profiles_dir or self.config_path.parent / "profiles"
        self.last_error: DS5ForgeError | None = None

    @classmethod
    def default(cls) -> ConfigRepository:
        return cls(
            config_path=Path(paths.config_file()),
            bundled_config_path=Path(paths.resource_path("resources/default_config.json")),
            bundled_profiles_dir=Path(paths.resource_path("resources/profiles")),
            user_profiles_dir=Path(paths.profiles_dir()),
        )

    def load(self) -> dict[str, Any]:
        try:
            bundled = self._read_json(self.bundled_config_path) if self.bundled_config_path else default_config()
            bundled = validate_config(bundled)
        except (OSError, json.JSONDecodeError, ConfigValidationError, TypeError, ValueError) as exc:
            LOGGER.error(
                "bundled config invalid; using compiled safe defaults",
                extra={"event": "config.bundle_invalid", "error": str(exc)},
            )
            bundled = default_config()
        try:
            missing = not self.config_path.exists()
            source = self._read_json(self.config_path) if not missing else bundled
            normalized = validate_config(source)
            if missing:
                try:
                    _atomic_json_write(self.config_path, normalized)
                except OSError as exc:
                    LOGGER.warning(
                        "initial config could not be created; keeping in-memory defaults",
                        extra={"event": "config.initial_save_failed", "path": str(self.config_path), "error": str(exc)},
                    )
            self.last_error = None
            return normalized
        except (OSError, json.JSONDecodeError, ConfigValidationError, TypeError, ValueError) as exc:
            self.last_error = DS5ForgeError(
                ErrorCode.CONFIG_LOAD_FAILED,
                "Saved configuration was invalid; safe defaults are active.",
                detail=str(exc),
                fields={"path": str(self.config_path)},
            )
            LOGGER.warning(
                "config load failed; using safe defaults", extra={"path": str(self.config_path), "error": str(exc)}
            )
            return validate_config(bundled if isinstance(bundled, Mapping) else default_config())

    def save(self, config: Mapping[str, Any]) -> dict[str, Any]:
        normalized = validate_config(config)
        try:
            _atomic_json_write(self.config_path, normalized)
        except OSError as exc:
            raise DS5ForgeError(
                ErrorCode.CONFIG_SAVE_FAILED,
                "Configuration could not be saved.",
                detail=str(exc),
                fields={"path": str(self.config_path)},
            ) from exc
        self.last_error = None
        return normalized

    def list_profiles(self) -> list[dict[str, Any]]:
        names: dict[str, dict[str, Any]] = {}
        # User profiles are indexed first so an identically named bundled
        # profile always wins below. Bundled presets are immutable authority.
        for directory, source, editable in (
            (self.user_profiles_dir, "user", True),
            (self.bundled_profiles_dir, "bundled", False),
        ):
            if directory is None or not directory.exists():
                continue
            for path in directory.glob("*.json"):
                name = path.stem
                if PROFILE_NAME_RE.fullmatch(name):
                    names[name.casefold()] = {"name": name, "source": source, "editable": editable}
        return sorted(names.values(), key=lambda item: item["name"].casefold())

    def load_profile(self, name: str) -> dict[str, Any]:
        path = self._profile_path(name, prefer_user=True)
        if path is None:
            raise ProfileNotFoundError(name)
        try:
            return validate_profile(self._read_json(path))
        except (OSError, json.JSONDecodeError, TypeError, ConfigValidationError) as exc:
            raise ConfigValidationError(
                "Profile is invalid and was not applied.",
                fields={"name": name},
                detail=str(exc),
            ) from exc

    def save_profile(self, name: str, profile: Mapping[str, Any]) -> dict[str, Any]:
        self._validate_name(name)
        if self._bundled_profile_path(name) is not None:
            raise ConfigValidationError(
                "Bundled profile names are reserved and cannot be overwritten.",
                fields={"name": name},
            )
        normalized = validate_profile(profile)
        path = self.user_profiles_dir / f"{name}.json"
        try:
            _atomic_json_write(path, normalized)
        except OSError as exc:
            raise DS5ForgeError(
                ErrorCode.CONFIG_SAVE_FAILED,
                "Profile could not be saved.",
                detail=str(exc),
                fields={"name": name},
            ) from exc
        return normalized

    def delete_profile(self, name: str) -> None:
        self._validate_name(name)
        path = self.user_profiles_dir / f"{name}.json"
        if not path.exists():
            raise ProfileNotFoundError(name)
        try:
            path.unlink()
        except OSError as exc:
            raise DS5ForgeError(
                ErrorCode.CONFIG_SAVE_FAILED,
                "Profile could not be deleted.",
                detail=str(exc),
                fields={"name": name},
            ) from exc

    def _profile_path(self, name: str, *, prefer_user: bool) -> Path | None:
        self._validate_name(name)
        bundled = self._bundled_profile_path(name)
        if bundled is not None:
            return bundled
        user = self.user_profiles_dir / f"{name}.json"
        if user.exists():
            return user
        return None

    def _bundled_profile_path(self, name: str) -> Path | None:
        if self.bundled_profiles_dir is None or not self.bundled_profiles_dir.exists():
            return None
        target = name.casefold()
        return next(
            (path for path in self.bundled_profiles_dir.glob("*.json") if path.stem.casefold() == target),
            None,
        )

    @staticmethod
    def _validate_name(name: str) -> None:
        if not isinstance(name, str) or not PROFILE_NAME_RE.fullmatch(name):
            raise ConfigValidationError(fields={"name": "must be 1-64 safe filename characters"})

    @staticmethod
    def _read_json(path: Path | None) -> Any:
        if path is None:
            return default_config()
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)


def _atomic_json_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            LOGGER.debug("temporary config cleanup failed", exc_info=True)
        raise
