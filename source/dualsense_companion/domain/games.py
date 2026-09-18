"""Platform-neutral P3 contracts for games, automation and compatibility.

The game-aware layer deliberately contains no process, Windows, controller or
web imports. Adapters turn observations into these immutable values before the
automation coordinator evaluates them.
"""

from __future__ import annotations

from collections.abc import Mapping as ABCMapping
from dataclasses import dataclass, fields, is_dataclass
from enum import StrEnum
from typing import Any


class ExitPolicy(StrEnum):
    RESTORE_PREVIOUS = "restore_previous"
    APPLY_DEFAULT = "apply_default"
    KEEP_CURRENT = "keep_current"


class CompatibilityMode(StrEnum):
    NATIVE = "native"
    REMAP = "remap"
    VIRTUAL = "virtual"


class AdaptiveTriggerMode(StrEnum):
    """Per-game ownership of DS5Forge-generated adaptive-trigger effects.

    ``NATIVE`` (the safe default) never synthesizes effects. ``REACTIVE`` is
    an explicit opt-in to a clearly-labeled DS5Forge-generated effect driven by
    real runtime signal. ``OFF`` neutralizes DS5Forge trigger output.
    """

    NATIVE = "native"
    REACTIVE = "reactive"
    OFF = "off"


class ProfileOrigin(StrEnum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"


class OutputKind(StrEnum):
    KEYBOARD = "keyboard"
    MOUSE = "mouse"
    LOGICAL = "logical"


@dataclass(frozen=True, slots=True)
class ForegroundApplication:
    """A best-effort foreground observation safe to publish to clients."""

    available: bool = False
    pid: int | None = None
    executable_name: str | None = None
    executable_path: str | None = None
    title: str | None = None
    observed_at: float = 0.0
    process_alive: bool = False
    diagnostic: str | None = None

    @property
    def context_key(self) -> tuple[Any, ...]:
        """Identity used for automation transitions; titles are excluded."""

        return (
            self.available,
            self.pid,
            (self.executable_name or "").casefold(),
            (self.executable_path or "").casefold(),
            self.process_alive,
        )

    @classmethod
    def desktop(cls, *, now: float = 0.0, diagnostic: str | None = None) -> ForegroundApplication:
        return cls(available=False, observed_at=now, process_alive=False, diagnostic=diagnostic)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class GameDefinition:
    """Persistent identity and action for one or more executable names."""

    id: str
    name: str
    executables: tuple[str, ...]
    executable_path: str | None = None
    profile: str = "Default"
    compatibility_mode: CompatibilityMode = CompatibilityMode.NATIVE
    adaptive_trigger_mode: AdaptiveTriggerMode = AdaptiveTriggerMode.NATIVE
    adaptive_trigger_strength: int = 45
    enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "executables", tuple(str(value) for value in self.executables))
        if not isinstance(self.adaptive_trigger_mode, AdaptiveTriggerMode):
            object.__setattr__(self, "adaptive_trigger_mode", AdaptiveTriggerMode(self.adaptive_trigger_mode))
        strength = int(self.adaptive_trigger_strength)
        if not 10 <= strength <= 100:
            raise ValueError("adaptive_trigger_strength must be between 10 and 100")
        object.__setattr__(self, "adaptive_trigger_strength", strength)

    def matches(self, foreground: ForegroundApplication) -> GameMatch:
        if not self.enabled:
            return GameMatch(
                game_id=self.id,
                game_name=self.name,
                matched=False,
                reason="Rule is disabled.",
                foreground=foreground,
            )
        if not foreground.available or not foreground.process_alive:
            return GameMatch(
                game_id=self.id,
                game_name=self.name,
                matched=False,
                reason="No live foreground process is available.",
                foreground=foreground,
            )
        observed_name = (foreground.executable_name or "").casefold()
        expected_names = {name.casefold() for name in self.executables}
        if observed_name not in expected_names:
            expected = ", ".join(self.executables)
            return GameMatch(
                game_id=self.id,
                game_name=self.name,
                matched=False,
                reason=(
                    f"Executable '{foreground.executable_name or 'unknown'}' does not match any configured executable "
                    f"({expected})."
                ),
                foreground=foreground,
            )
        if self.executable_path:
            observed_path = (foreground.executable_path or "").casefold()
            if not observed_path:
                return GameMatch(
                    game_id=self.id,
                    game_name=self.name,
                    matched=False,
                    reason="Executable name matched, but its full path was unavailable.",
                    foreground=foreground,
                )
            if observed_path != self.executable_path.casefold():
                return GameMatch(
                    game_id=self.id,
                    game_name=self.name,
                    matched=False,
                    reason=f"Executable path does not match '{self.executable_path}'.",
                    foreground=foreground,
                )
        return GameMatch(
            game_id=self.id,
            game_name=self.name,
            matched=True,
            reason="Executable name and configured path matched.",
            foreground=foreground,
        )

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class GameMatch:
    game_id: str | None
    matched: bool
    reason: str
    foreground: ForegroundApplication
    game_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    game_id: str
    game_name: str
    matched: bool
    reason: str
    action: str = "none"
    profile: str | None = None
    compatibility_mode: CompatibilityMode | None = None

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class OutputTarget:
    kind: OutputKind | str
    code: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", OutputKind(self.kind))
        object.__setattr__(self, "code", str(self.code))

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class Mapping:
    id: str
    input: str
    output: OutputTarget
    game_id: str | None = None
    enabled: bool = True
    debounce_ms: int = 25

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class Chord:
    id: str
    inputs: tuple[str, ...]
    output: OutputTarget
    game_id: str | None = None
    enabled: bool = True
    window_ms: int = 250
    debounce_ms: int = 25

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", tuple(str(value) for value in self.inputs))
        if not isinstance(self.output, OutputTarget):
            object.__setattr__(self, "output", OutputTarget(**self.output))

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class VirtualControllerCapability:
    installed: bool = False
    available: bool = False
    physical_suppression_supported: bool = False
    provider: str | None = None
    reason: str | None = "No approved virtual-controller provider is installed."

    @property
    def operational(self) -> bool:
        return self.installed and self.available and self.physical_suppression_supported

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class CompatibilityState:
    mode: CompatibilityMode = CompatibilityMode.NATIVE
    available: bool = True
    virtual_capability: VirtualControllerCapability = VirtualControllerCapability()
    physical_input_visible: bool = True
    virtual_input_active: bool = False
    physical_suppression_active: bool = False
    double_input_risk: bool = False
    reason: str | None = None
    changed_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class AutomationState:
    enabled: bool = False
    exit_policy: ExitPolicy = ExitPolicy.RESTORE_PREVIOUS
    default_profile: str = "Default"
    active_game_id: str | None = None
    active_game_name: str | None = None
    active_profile: str = "Default"
    profile_origin: ProfileOrigin = ProfileOrigin.MANUAL
    manual_override: bool = False
    last_match: GameMatch | None = None
    rule_evaluations: tuple[RuleEvaluation, ...] = ()
    previous_profile: str | None = None
    previous_compatibility_mode: CompatibilityMode | None = None
    transition: int = 0
    last_transition_at: float = 0.0
    status: str = "idle"
    diagnostic: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_evaluations", tuple(self.rule_evaluations))

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class SyntheticOutput:
    kind: OutputKind | str
    code: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", OutputKind(self.kind))
        object.__setattr__(self, "code", str(self.code))

    @classmethod
    def from_target(cls, target: OutputTarget) -> SyntheticOutput:
        return cls(target.kind, target.code)

    @property
    def key(self) -> str:
        kind = self.kind.value if isinstance(self.kind, OutputKind) else self.kind
        return f"{kind}:{self.code.casefold()}"

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class ReleaseReport:
    reason: str
    released: tuple[SyntheticOutput, ...] = ()
    failures: tuple[str, ...] = ()
    completed: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "released", tuple(self.released))
        object.__setattr__(self, "failures", tuple(self.failures))
        object.__setattr__(self, "completed", not bool(self.failures))

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class SyntheticOutputState:
    held: tuple[SyntheticOutput, ...] = ()
    last_release: ReleaseReport | None = None
    release_status: str = "idle"

    def __post_init__(self) -> None:
        object.__setattr__(self, "held", tuple(self.held))

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class ConflictDiagnostic:
    process: str
    running: bool
    severity: str
    message: str
    evidence: str | None = None
    checked_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


def _jsonable(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, ABCMapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if is_dataclass(value):
        return {item.name: _jsonable(getattr(value, item.name)) for item in fields(value)}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value
