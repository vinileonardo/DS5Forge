"""Strict, atomic persistence for the P3 game and automation registry."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping as ABCMapping
from pathlib import Path
from typing import Any

from .. import paths
from ..diagnostics.logging import get_logger
from ..domain.errors import DS5ForgeError, ErrorCode
from ..domain.games import (
    Chord,
    CompatibilityMode,
    ExitPolicy,
    GameDefinition,
    Mapping,
    OutputKind,
    OutputTarget,
)
from .config import PROFILE_NAME_RE, _atomic_json_write

LOGGER = get_logger(__name__)
GAME_REGISTRY_SCHEMA_VERSION = 2
MAX_GAMES = 256
MAX_EXECUTABLES_PER_GAME = 16
MAX_MAPPINGS = 512
MAX_CHORDS = 256
DEFAULT_CONFLICT_PROCESSES = (
    "steam.exe",
    "ds4windows.exe",
    "rewasd.exe",
    "joytokey.exe",
    "antimicrox.exe",
)
CONTROLLER_INPUTS = frozenset(
    {
        "square",
        "triangle",
        "circle",
        "cross",
        "dpad_up",
        "dpad_down",
        "dpad_left",
        "dpad_right",
        "l1",
        "r1",
        "l2",
        "r2",
        "l3",
        "r3",
        "options",
        "share",
        "ps",
        "mic_button",
        "touchpad_button",
    }
)
MAX_KEY_COMBO_PARTS = 4
KEYBOARD_SPECIAL_OUTPUTS = frozenset(
    {
        "BACKSPACE",
        "TAB",
        "ENTER",
        "SHIFT",
        "CTRL",
        "ALT",
        "PAUSE",
        "CAPSLOCK",
        "ESC",
        "SPACE",
        "PAGEUP",
        "PAGEDOWN",
        "END",
        "HOME",
        "LEFT",
        "UP",
        "RIGHT",
        "DOWN",
        "INSERT",
        "DELETE",
        "WIN",
        *(f"F{index}" for index in range(1, 13)),
    }
)
KEYBOARD_OUTPUT_ALIASES = {
    "CONTROL": "CTRL",
    "ESCAPE": "ESC",
    "RETURN": "ENTER",
    "WINDOWS": "WIN",
}
MOUSE_OUTPUT_ALIASES = {
    "left": "left",
    "left_button": "left",
    "lmb": "left",
    "right": "right",
    "right_button": "right",
    "rmb": "right",
    "middle": "middle",
    "middle_button": "middle",
    "mmb": "middle",
    "mouse4": "mouse4",
    "x1": "mouse4",
    "xbutton1": "mouse4",
    "mouse5": "mouse5",
    "x2": "mouse5",
    "xbutton2": "mouse5",
}


def default_games_config() -> dict[str, Any]:
    return {
        "schema_version": GAME_REGISTRY_SCHEMA_VERSION,
        "games": [],
        "automation": {
            "enabled": False,
            "exit_policy": ExitPolicy.RESTORE_PREVIOUS.value,
            "default_profile": "Default",
        },
        "mappings": [],
        "chords": [],
        "compatibility_preference": CompatibilityMode.NATIVE.value,
        "conflict_processes": list(DEFAULT_CONFLICT_PROCESSES),
    }


class GameRegistryValidationError(DS5ForgeError):
    def __init__(
        self,
        message: str = "Game registry is invalid.",
        *,
        fields: ABCMapping[str, Any] | None = None,
        code: ErrorCode = ErrorCode.GAME_REGISTRY_INVALID,
    ) -> None:
        super().__init__(code, message, fields=fields)


class GameNotFoundError(DS5ForgeError):
    def __init__(self, game_id: str) -> None:
        super().__init__(ErrorCode.GAME_NOT_FOUND, f"Game '{game_id}' was not found.", fields={"id": game_id})


def _migrate_games_config(config: Any) -> Any:
    """Migrate the unreleased P3 schema-v1 single executable shape to v2."""

    if not isinstance(config, ABCMapping) or config.get("schema_version") != 1:
        return config
    migrated = copy.deepcopy(dict(config))
    games = migrated.get("games")
    if isinstance(games, list):
        for item in games:
            if isinstance(item, dict) and "executables" not in item and "executable" in item:
                item["executables"] = [item.pop("executable")]
    migrated["schema_version"] = GAME_REGISTRY_SCHEMA_VERSION
    return migrated


def validate_games_config(config: ABCMapping[str, Any]) -> dict[str, Any]:
    """Validate the complete P3 document before any state is replaced."""

    if not isinstance(config, ABCMapping):
        raise GameRegistryValidationError(fields={"registry": "must be an object"})
    allowed = {
        "schema_version",
        "games",
        "automation",
        "mappings",
        "chords",
        "compatibility_preference",
        "conflict_processes",
    }
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise GameRegistryValidationError(fields={"unknown": unknown})
    if config.get("schema_version") != GAME_REGISTRY_SCHEMA_VERSION or isinstance(config.get("schema_version"), bool):
        raise GameRegistryValidationError(
            fields={"schema_version": f"expected {GAME_REGISTRY_SCHEMA_VERSION} as an integer"}
        )

    games = _validate_games(config.get("games"))
    game_ids = {item["id"].casefold() for item in games}
    automation = _validate_automation(config.get("automation"))
    mappings = _validate_mappings(config.get("mappings"), game_ids)
    chords = _validate_chords(config.get("chords"), game_ids)
    preference = _strict_choice(config.get("compatibility_preference"), CompatibilityMode, "compatibility_preference")
    conflicts = _validate_conflict_processes(config.get("conflict_processes"))
    return {
        "schema_version": GAME_REGISTRY_SCHEMA_VERSION,
        "games": games,
        "automation": automation,
        "mappings": mappings,
        "chords": chords,
        "compatibility_preference": preference,
        "conflict_processes": conflicts,
    }


def game_definitions(document: ABCMapping[str, Any]) -> tuple[GameDefinition, ...]:
    return tuple(
        GameDefinition(
            id=item["id"],
            name=item["name"],
            executables=tuple(item["executables"]),
            executable_path=item["executable_path"],
            profile=item["profile"],
            compatibility_mode=CompatibilityMode(item["compatibility_mode"]),
            enabled=item["enabled"],
        )
        for item in document["games"]
    )


def mapping_definitions(document: ABCMapping[str, Any]) -> tuple[Mapping, ...]:
    return tuple(
        Mapping(
            id=item["id"],
            input=item["input"],
            output=OutputTarget(kind=item["output_kind"], code=item["output_code"]),
            game_id=item["game_id"],
            enabled=item["enabled"],
            debounce_ms=item["debounce_ms"],
        )
        for item in document["mappings"]
    )


def chord_definitions(document: ABCMapping[str, Any]) -> tuple[Chord, ...]:
    return tuple(
        Chord(
            id=item["id"],
            inputs=tuple(item["inputs"]),
            output=OutputTarget(kind=item["output_kind"], code=item["output_code"]),
            game_id=item["game_id"],
            enabled=item["enabled"],
            window_ms=item["window_ms"],
            debounce_ms=item["debounce_ms"],
        )
        for item in document["chords"]
    )


class GameRegistryRepository:
    """A separate P3 file with valid-in-memory recovery and atomic writes."""

    def __init__(self, *, path: Path) -> None:
        self.path = Path(path)
        self.last_error: DS5ForgeError | None = None

    @classmethod
    def default(cls) -> GameRegistryRepository:
        return cls(path=Path(paths.games_file()))

    def load(self) -> dict[str, Any]:
        defaults = default_games_config()
        if not self.path.exists():
            try:
                normalized = validate_games_config(defaults)
                _atomic_json_write(self.path, normalized)
            except OSError as exc:
                LOGGER.warning(
                    "initial game registry could not be created",
                    extra={"event": "game_registry.initial_save_failed", "path": str(self.path), "error": str(exc)},
                )
            self.last_error = None
            return normalized
        try:
            with self.path.open("r", encoding="utf-8-sig") as handle:
                raw = json.load(handle, parse_constant=_reject_json_constant)
            normalized = validate_games_config(_migrate_games_config(raw))
            self.last_error = None
            return normalized
        except (OSError, json.JSONDecodeError, TypeError, ValueError, GameRegistryValidationError) as exc:
            self.last_error = DS5ForgeError(
                ErrorCode.GAME_REGISTRY_LOAD_FAILED,
                "Saved game registry was invalid; safe defaults are active in memory.",
                detail=str(exc),
                fields={"path": str(self.path)},
            )
            LOGGER.warning(
                "game registry load failed; using safe defaults",
                extra={"event": "game_registry.load_failed", "path": str(self.path), "error": str(exc)},
            )
            return defaults

    def save(self, config: ABCMapping[str, Any]) -> dict[str, Any]:
        normalized = validate_games_config(config)
        try:
            _atomic_json_write(self.path, normalized)
        except OSError as exc:
            raise DS5ForgeError(
                ErrorCode.GAME_REGISTRY_SAVE_FAILED,
                "Game registry could not be saved; current state was not changed.",
                detail=str(exc),
                fields={"path": str(self.path)},
            ) from exc
        self.last_error = None
        return normalized

    def get(self, game_id: str) -> dict[str, Any]:
        document = self.load()
        target = game_id.casefold()
        for item in document["games"]:
            if item["id"].casefold() == target:
                return copy.deepcopy(item)
        raise GameNotFoundError(game_id)


def _validate_games(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise GameRegistryValidationError(fields={"games": "must be an array"})
    if len(value) > MAX_GAMES:
        raise GameRegistryValidationError(fields={"games": f"maximum is {MAX_GAMES}"})
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    allowed = {"id", "name", "executables", "executable_path", "profile", "compatibility_mode", "enabled"}
    for index, raw in enumerate(value):
        prefix = f"games.{index}"
        if not isinstance(raw, ABCMapping):
            raise GameRegistryValidationError(fields={prefix: "must be an object"})
        unknown = sorted(set(raw) - allowed)
        if unknown:
            raise GameRegistryValidationError(fields={f"{prefix}.unknown": unknown})
        game_id = _strict_string(raw.get("id"), f"{prefix}.id", max_length=64)
        if not _valid_identifier(game_id):
            raise GameRegistryValidationError(fields={f"{prefix}.id": "must be a simple unique identifier"})
        folded = game_id.casefold()
        if folded in seen:
            raise GameRegistryValidationError(fields={f"{prefix}.id": "duplicate game id"})
        seen.add(folded)
        name = _strict_string(raw.get("name"), f"{prefix}.name", max_length=100)
        executables = _validate_executables(raw.get("executables"), f"{prefix}.executables")
        executable_path = raw.get("executable_path")
        if executable_path is not None:
            executable_path = _strict_string(executable_path, f"{prefix}.executable_path", max_length=520)
            if not executable_path:
                raise GameRegistryValidationError(fields={f"{prefix}.executable_path": "may not be empty"})
            if len(executables) != 1:
                raise GameRegistryValidationError(
                    fields={f"{prefix}.executable_path": "requires exactly one configured executable"}
                )
        profile = _strict_string(raw.get("profile", "Default"), f"{prefix}.profile", max_length=64)
        if not PROFILE_NAME_RE.fullmatch(profile):
            raise GameRegistryValidationError(fields={f"{prefix}.profile": "is not a valid profile name"})
        mode = _strict_choice(
            raw.get("compatibility_mode", CompatibilityMode.NATIVE.value),
            CompatibilityMode,
            prefix + ".compatibility_mode",
        )
        enabled = _strict_bool(raw.get("enabled", True), f"{prefix}.enabled")
        result.append(
            {
                "id": game_id,
                "name": name,
                "executables": executables,
                "executable_path": executable_path,
                "profile": profile,
                "compatibility_mode": mode,
                "enabled": enabled,
            }
        )
    return result


def _validate_executables(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_EXECUTABLES_PER_GAME:
        raise GameRegistryValidationError(
            fields={field: f"must contain between 1 and {MAX_EXECUTABLES_PER_GAME} executable names"}
        )
    result: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        executable = _strict_string(item, f"{field}.{index}", max_length=260)
        if any(char in executable for char in ("/", "\\", "\x00")):
            raise GameRegistryValidationError(fields={f"{field}.{index}": "must be an executable name, not a path"})
        folded = executable.casefold()
        if folded in seen:
            raise GameRegistryValidationError(fields={f"{field}.{index}": "duplicate executable name"})
        seen.add(folded)
        result.append(executable)
    return result


def _validate_automation(value: Any) -> dict[str, Any]:
    if not isinstance(value, ABCMapping):
        raise GameRegistryValidationError(fields={"automation": "must be an object"})
    allowed = {"enabled", "exit_policy", "default_profile"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise GameRegistryValidationError(fields={"automation.unknown": unknown})
    return {
        "enabled": _strict_bool(value.get("enabled", False), "automation.enabled"),
        "exit_policy": _strict_choice(
            value.get("exit_policy", ExitPolicy.RESTORE_PREVIOUS.value), ExitPolicy, "automation.exit_policy"
        ),
        "default_profile": _valid_profile_name(value.get("default_profile", "Default"), "automation.default_profile"),
    }


def _validate_mappings(value: Any, game_ids: set[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise GameRegistryValidationError(fields={"mappings": "must be an array"})
    if len(value) > MAX_MAPPINGS:
        raise GameRegistryValidationError(fields={"mappings": f"maximum is {MAX_MAPPINGS}"})
    allowed = {"id", "input", "output_kind", "output_code", "game_id", "enabled", "debounce_ms"}
    result: list[dict[str, Any]] = []
    ids: set[str] = set()
    sources: set[tuple[str | None, str]] = set()
    for index, raw in enumerate(value):
        prefix = f"mappings.{index}"
        if not isinstance(raw, ABCMapping):
            raise GameRegistryValidationError(fields={prefix: "must be an object"})
        unknown = sorted(set(raw) - allowed)
        if unknown:
            raise GameRegistryValidationError(fields={f"{prefix}.unknown": unknown})
        item = _validate_output_item(raw, prefix, is_chord=False, game_ids=game_ids)
        folded_id = item["id"].casefold()
        source = ((item["game_id"].casefold() if item["game_id"] else None), item["input"])
        if folded_id in ids:
            raise GameRegistryValidationError(fields={f"{prefix}.id": "duplicate mapping id"})
        if any(
            existing_input == item["input"] and _scopes_overlap(existing_scope, item["game_id"])
            for existing_scope, existing_input in sources
        ):
            raise GameRegistryValidationError(
                "Mapping input conflicts with another mapping that can be active in the same context.",
                code=ErrorCode.MAPPING_CONFLICT,
                fields={f"{prefix}.input": "conflicts with another mapping in an overlapping scope"},
            )
        ids.add(folded_id)
        sources.add(source)
        result.append(item)
    return result


def _validate_chords(value: Any, game_ids: set[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise GameRegistryValidationError(fields={"chords": "must be an array"})
    if len(value) > MAX_CHORDS:
        raise GameRegistryValidationError(fields={"chords": f"maximum is {MAX_CHORDS}"})
    allowed = {
        "id",
        "inputs",
        "output_kind",
        "output_code",
        "game_id",
        "enabled",
        "window_ms",
        "debounce_ms",
    }
    result: list[dict[str, Any]] = []
    ids: set[str] = set()
    signatures: set[tuple[str | None, frozenset[str]]] = set()
    for index, raw in enumerate(value):
        prefix = f"chords.{index}"
        if not isinstance(raw, ABCMapping):
            raise GameRegistryValidationError(fields={prefix: "must be an object"})
        unknown = sorted(set(raw) - allowed)
        if unknown:
            raise GameRegistryValidationError(fields={f"{prefix}.unknown": unknown})
        item = _validate_output_item(raw, prefix, is_chord=True, game_ids=game_ids)
        inputs = raw.get("inputs")
        if not isinstance(inputs, list) or len(inputs) < 2:
            raise GameRegistryValidationError(fields={f"{prefix}.inputs": "must contain at least two inputs"})
        normalized_inputs: list[str] = []
        for input_name in inputs:
            name = _strict_string(input_name, f"{prefix}.inputs", max_length=32)
            if name not in CONTROLLER_INPUTS:
                raise GameRegistryValidationError(fields={f"{prefix}.inputs": f"unsupported controller input '{name}'"})
            normalized_inputs.append(name)
        if len(set(normalized_inputs)) != len(normalized_inputs):
            raise GameRegistryValidationError(fields={f"{prefix}.inputs": "may not contain duplicates"})
        item["inputs"] = normalized_inputs
        item["window_ms"] = _bounded_int(raw.get("window_ms", 250), f"{prefix}.window_ms", 25, 1_000)
        item["debounce_ms"] = _bounded_int(raw.get("debounce_ms", 25), f"{prefix}.debounce_ms", 1, 500)
        folded_id = item["id"].casefold()
        scope = item["game_id"].casefold() if item["game_id"] else None
        signature = (scope, frozenset(normalized_inputs))
        if folded_id in ids:
            raise GameRegistryValidationError(fields={f"{prefix}.id": "duplicate chord id"})
        if any(
            _scopes_overlap(existing_scope, scope)
            and (existing_inputs <= signature[1] or signature[1] <= existing_inputs)
            for existing_scope, existing_inputs in signatures
        ):
            raise GameRegistryValidationError(
                "Chord inputs are ambiguous with another chord in an overlapping scope.",
                code=ErrorCode.CHORD_CONFLICT,
                fields={f"{prefix}.inputs": "duplicate or subset chord overlaps another active chord"},
            )
        ids.add(folded_id)
        signatures.add(signature)
        result.append(item)
    return result


def _validate_output_item(
    raw: ABCMapping[str, Any], prefix: str, *, is_chord: bool, game_ids: set[str]
) -> dict[str, Any]:
    output_kind = _strict_choice(raw.get("output_kind"), OutputKind, f"{prefix}.output_kind")
    output_code = _strict_string(raw.get("output_code"), f"{prefix}.output_code", max_length=64)
    item: dict[str, Any] = {
        "id": _strict_string(raw.get("id"), f"{prefix}.id", max_length=64),
        "input": "",
        "output_kind": output_kind,
        "output_code": _validate_output_code(output_kind, output_code, f"{prefix}.output_code"),
        "game_id": None,
        "enabled": _strict_bool(raw.get("enabled", True), f"{prefix}.enabled"),
    }
    if not is_chord:
        input_name = _strict_string(raw.get("input"), f"{prefix}.input", max_length=32)
        if input_name not in CONTROLLER_INPUTS:
            raise GameRegistryValidationError(fields={f"{prefix}.input": "unsupported controller input"})
        item["input"] = input_name
        item["debounce_ms"] = _bounded_int(raw.get("debounce_ms", 25), f"{prefix}.debounce_ms", 1, 500)
    game_id = raw.get("game_id")
    if game_id is not None:
        game_id = _strict_string(game_id, f"{prefix}.game_id", max_length=64)
        if game_id.casefold() not in game_ids:
            raise GameRegistryValidationError(fields={f"{prefix}.game_id": "does not reference a registered game"})
    item["game_id"] = game_id
    return item


def _validate_output_code(kind: str, code: str, field: str) -> str:
    if kind == OutputKind.KEYBOARD.value:
        parts = code.split("+")
        if not 1 <= len(parts) <= MAX_KEY_COMBO_PARTS:
            raise GameRegistryValidationError(
                fields={field: f"keyboard combinations support between 1 and {MAX_KEY_COMBO_PARTS} keys"}
            )
        normalized_parts: list[str] = []
        seen: set[str] = set()
        for index, part in enumerate(parts):
            normalized = part.strip().upper()
            normalized = KEYBOARD_OUTPUT_ALIASES.get(normalized, normalized)
            valid = (len(normalized) == 1 and ("A" <= normalized <= "Z" or "0" <= normalized <= "9")) or (
                normalized in KEYBOARD_SPECIAL_OUTPUTS
            )
            if not valid:
                raise GameRegistryValidationError(
                    fields={
                        field: ("unsupported keyboard output; use A-Z, 0-9, common navigation/modifier keys or F1-F12")
                    }
                )
            if normalized in seen:
                raise GameRegistryValidationError(
                    fields={field: f"duplicate key '{normalized}' at position {index + 1}"}
                )
            seen.add(normalized)
            normalized_parts.append(normalized)
        return "+".join(normalized_parts)
    if kind == OutputKind.MOUSE.value:
        normalized = code.casefold()
        if normalized in MOUSE_OUTPUT_ALIASES:
            return MOUSE_OUTPUT_ALIASES[normalized]
        raise GameRegistryValidationError(
            fields={field: "unsupported mouse output; use left, right, middle, mouse4 or mouse5"}
        )
    if kind == OutputKind.LOGICAL.value:
        raise GameRegistryValidationError(
            fields={field: "logical output is unavailable until an explicit production adapter is configured"}
        )
    raise GameRegistryValidationError(fields={field: "unsupported output kind"})


def _validate_conflict_processes(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise GameRegistryValidationError(fields={"conflict_processes": "must be an array"})
    result: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        name = _strict_string(item, f"conflict_processes.{index}", max_length=260)
        if not name or any(char in name for char in ("/", "\\", "\x00")):
            raise GameRegistryValidationError(fields={f"conflict_processes.{index}": "must be a process name"})
        if name.casefold() not in seen:
            result.append(name)
            seen.add(name.casefold())
    return result


def _strict_string(value: Any, field: str, *, max_length: int) -> str:
    if not isinstance(value, str):
        raise GameRegistryValidationError(fields={field: "must be a string"})
    if not value.strip() or len(value) > max_length or "\x00" in value:
        raise GameRegistryValidationError(fields={field: "is empty, too long or contains a NUL"})
    return value.strip()


def _strict_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise GameRegistryValidationError(fields={field: "must be a boolean"})
    return value


def _bounded_int(value: Any, field: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise GameRegistryValidationError(fields={field: f"must be an integer between {minimum} and {maximum}"})
    return value


def _strict_choice(value: Any, enum_type: Any, field: str) -> str:
    if not isinstance(value, str):
        raise GameRegistryValidationError(fields={field: "must be a string"})
    choices = {item.value for item in enum_type}
    if value not in choices:
        raise GameRegistryValidationError(fields={field: f"must be one of {sorted(choices)}"})
    return value


def _valid_profile_name(value: Any, field: str) -> str:
    name = _strict_string(value, field, max_length=64)
    if not PROFILE_NAME_RE.fullmatch(name):
        raise GameRegistryValidationError(fields={field: "is not a valid profile name"})
    return name


def _valid_identifier(value: str) -> bool:
    return value[0].isalnum() and all(char.isalnum() or char in "._-" for char in value)


def _scopes_overlap(left: str | None, right: str | None) -> bool:
    return left is None or right is None or left.casefold() == right.casefold()


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")
