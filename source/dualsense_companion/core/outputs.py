"""Common ownership and remapping engine for synthetic outputs."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from collections.abc import Mapping as ABCMapping

from ..diagnostics.logging import get_logger
from ..domain.errors import DS5ForgeError, ErrorCode
from ..domain.games import Chord, Mapping, OutputKind, OutputTarget, ReleaseReport, SyntheticOutput
from .ports import KeyboardOutput, MouseOutput, VirtualControllerProvider

LOGGER = get_logger(__name__)


class OutputManager:
    """Own every synthetic key/button and release all surfaces best-effort."""

    def __init__(
        self,
        mouse: MouseOutput,
        *,
        keyboard: KeyboardOutput | None = None,
        virtual_provider: VirtualControllerProvider | None = None,
        logical_output: Callable[[str, bool], None] | None = None,
    ) -> None:
        self.mouse = mouse
        self.keyboard = keyboard
        self.virtual_provider = virtual_provider
        self.logical_output = logical_output
        self._virtual_active = False
        self._held: dict[str, SyntheticOutput] = {}
        self._owners: dict[str, int] = {}
        self._lock = threading.RLock()

    @property
    def held(self) -> tuple[SyntheticOutput, ...]:
        with self._lock:
            return tuple(self._held.values())

    def press(self, target: OutputTarget | SyntheticOutput) -> bool:
        output = _as_output(target)
        with self._lock:
            if output.key in self._owners:
                self._owners[output.key] += 1
                return False
            self._send(output, True)
            self._held[output.key] = output
            self._owners[output.key] = 1
            return True

    def release(self, target: OutputTarget | SyntheticOutput) -> bool:
        output = _as_output(target)
        with self._lock:
            held = self._held.get(output.key)
            if held is None:
                return False
            owners = self._owners.get(output.key, 1)
            if owners > 1:
                self._owners[output.key] = owners - 1
                return False
            self._send(held, False)
            self._held.pop(output.key, None)
            self._owners.pop(output.key, None)
            return True

    def release_all(self, reason: str = "release_all") -> ReleaseReport:
        """Attempt every held release and every adapter-level cleanup.

        One broken SendInput call must not prevent another held key, mouse
        button or virtual button from being released.
        """

        with self._lock:
            held = tuple(self._held.values())
            self._held.clear()
            self._owners.clear()
        released: list[SyntheticOutput] = []
        failures: list[str] = []
        for output in held:
            try:
                self._send(output, False)
                released.append(output)
            except Exception as exc:
                failures.append(f"{output.key}: {exc}")
                LOGGER.warning(
                    "synthetic output release failed",
                    extra={"event": "synthetic.release_failed", "output": output.key, "error": str(exc)},
                )
        # Adapter-level cleanup covers ownership created by touchpad and any
        # provider state not represented in the remapper's local held set.
        for name, adapter in (
            ("mouse", self.mouse),
            ("keyboard", self.keyboard),
            ("virtual", self.virtual_provider),
        ):
            if adapter is None:
                continue
            try:
                adapter.release_all()
            except Exception as exc:
                failures.append(f"{name}: {exc}")
                LOGGER.warning(
                    "synthetic adapter cleanup failed",
                    extra={"event": "synthetic.release_failed", "output": name, "error": str(exc)},
                )
        return ReleaseReport(reason=reason, released=tuple(released), failures=tuple(failures))

    def set_virtual_active(self, active: bool) -> None:
        with self._lock:
            self._virtual_active = bool(active)

    def _send(self, output: SyntheticOutput, down: bool) -> None:
        try:
            if output.kind == OutputKind.KEYBOARD:
                if self.keyboard is None:
                    raise DS5ForgeError(
                        ErrorCode.SYNTHETIC_OUTPUT_FAILED,
                        "Keyboard output is unavailable on this platform.",
                        fields={"output": output.to_dict()},
                    )
                self.keyboard.key(output.code, down)
                return
            if output.kind == OutputKind.MOUSE:
                mapped_button = getattr(self.mouse, "button_code", None)
                if callable(mapped_button):
                    mapped_button(output.code, down)
                    return
                # Preserve compatibility with the original left/right-only
                # pointer port used by touchpad tests and legacy adapters.
                self.mouse.button(_legacy_mouse_side(output.code), down)
                return
            if self.logical_output is not None:
                self.logical_output(output.code, down)
                return
            if self._virtual_active and self.virtual_provider is not None:
                self.virtual_provider.send_button(output.code, down)
                return
            raise DS5ForgeError(
                ErrorCode.SYNTHETIC_OUTPUT_FAILED,
                "Logical output is unavailable because no provider is configured.",
                fields={"output": output.to_dict()},
            )
        except DS5ForgeError:
            raise
        except Exception as exc:
            raise DS5ForgeError(
                ErrorCode.SYNTHETIC_OUTPUT_FAILED,
                "Synthetic output failed.",
                detail=str(exc),
                fields={"output": output.to_dict(), "down": down},
            ) from exc


class RemappingEngine:
    """Edge-driven mapping/chord interpreter with deterministic precedence."""

    def __init__(
        self,
        output_manager: OutputManager,
        *,
        mappings: Sequence[Mapping] = (),
        chords: Sequence[Chord] = (),
    ) -> None:
        self.output_manager = output_manager
        self._mappings: tuple[Mapping, ...] = tuple(mappings)
        self._chords: tuple[Chord, ...] = tuple(chords)
        self._pressed: set[str] = set()
        self._pressed_since: dict[str, float] = {}
        self._last_edge: dict[str, float] = {}
        self._pending_mappings: dict[str, Mapping] = {}
        self._active_mappings: dict[str, Mapping] = {}
        self._active_chords: dict[str, Chord] = {}
        self._fired_chords: set[str] = set()
        self._game_id: str | None = None
        self._lock = threading.RLock()

    @property
    def mappings(self) -> tuple[Mapping, ...]:
        return self._mappings

    @property
    def chords(self) -> tuple[Chord, ...]:
        return self._chords

    def configure(self, mappings: Sequence[Mapping], chords: Sequence[Chord]) -> None:
        with self._lock:
            self.release_all(reason="configuration_change")
            self._mappings = tuple(mappings)
            self._chords = tuple(chords)

    @property
    def game_id(self) -> str | None:
        with self._lock:
            return self._game_id

    def set_game_context(self, game_id: str | None, *, release: bool = True) -> ReleaseReport | None:
        """Switch the scoped mapping context after releasing old ownership."""

        normalized = game_id.casefold() if game_id is not None else None
        with self._lock:
            if self._game_id == normalized:
                return None
            report = self.release_all(reason="game_context_change") if release else None
            self._game_id = normalized
            return report

    def process(self, buttons: ABCMapping[str, bool], *, now: float | None = None) -> None:
        """Process one normalized controller edge snapshot.

        Simple mappings are held back while an input can still complete a
        chord. If the chord window expires, the simple mapping is emitted.
        """

        timestamp = time.monotonic() if now is None else float(now)
        with self._lock:
            try:
                raw_pressed = {str(name) for name, value in buttons.items() if bool(value)}
                current = self._debounced_pressed(raw_pressed, timestamp)
                previous = set(self._pressed)
                rising = current - previous
                falling = previous - current
                self._pressed = current
                for name in rising:
                    self._pressed_since.setdefault(name, timestamp)
                for name in falling:
                    self._pressed_since.pop(name, None)

                self._release_fallen(falling)
                if not current:
                    self._fired_chords.clear()

                completed = self._completed_chords(timestamp)
                selected: Chord | None = None
                if completed:
                    selected = sorted(completed, key=lambda item: (-len(item.inputs), item.id.casefold()))[0]
                    self.output_manager.press(selected.output)
                    self._active_chords[selected.id] = selected
                    self._fired_chords.add(selected.id)
                    for input_name in selected.inputs:
                        self._pending_mappings.pop(input_name, None)
                    # A completed chord wins over all simple mappings that
                    # share its inputs, even if they were queued this frame.
                    for mapping_id, mapping in tuple(self._active_mappings.items()):
                        if mapping.input in selected.inputs:
                            self.output_manager.release(mapping.output)
                            self._active_mappings.pop(mapping_id, None)

                for mapping in self._mappings:
                    if not mapping.enabled or not self._scope_matches(mapping) or mapping.input not in rising:
                        continue
                    if selected is not None and mapping.input in selected.inputs:
                        # A chord completed on this edge, so its inputs must
                        # not also start simple mappings in the same frame.
                        continue
                    if self._has_possible_chord(mapping.input):
                        self._pending_mappings[mapping.input] = mapping
                    else:
                        self._press_mapping(mapping)

                self._flush_due_mappings(timestamp)
                self._release_finished_chords()
            except Exception:
                self.release_all(reason="remap_exception")
                raise

    def release_all(self, *, reason: str = "remap_release") -> ReleaseReport:
        with self._lock:
            report = self.output_manager.release_all(reason)
            self._pressed.clear()
            self._pressed_since.clear()
            self._last_edge.clear()
            self._pending_mappings.clear()
            self._active_mappings.clear()
            self._active_chords.clear()
            self._fired_chords.clear()
            return report

    def _debounced_pressed(self, raw_pressed: set[str], now: float) -> set[str]:
        accepted = set(self._pressed)
        names = accepted | raw_pressed | set(self._pressed_since)
        for name in names:
            raw_value = name in raw_pressed
            current_value = name in accepted
            if raw_value == current_value:
                continue
            debounce_ms = self._debounce_for(name)
            previous_edge = self._last_edge.get(name)
            if previous_edge is not None and (now - previous_edge) * 1000 < debounce_ms:
                continue
            if raw_value:
                accepted.add(name)
            else:
                accepted.discard(name)
            self._last_edge[name] = now
        return accepted

    def _debounce_for(self, input_name: str) -> int:
        values = [
            item.debounce_ms
            for item in self._mappings
            if item.enabled and self._scope_matches(item) and item.input == input_name
        ]
        values.extend(
            item.debounce_ms
            for item in self._chords
            if item.enabled and self._scope_matches(item) and input_name in item.inputs
        )
        return min(values) if values else 25

    def _has_possible_chord(self, input_name: str) -> bool:
        return any(
            chord.enabled
            and self._scope_matches(chord)
            and input_name in chord.inputs
            and chord.id not in self._fired_chords
            for chord in self._chords
        )

    def _completed_chords(self, now: float) -> list[Chord]:
        completed: list[Chord] = []
        for chord in self._chords:
            if (
                not chord.enabled
                or not self._scope_matches(chord)
                or chord.id in self._fired_chords
                or not set(chord.inputs).issubset(self._pressed)
            ):
                continue
            starts = [self._pressed_since.get(name, now) for name in chord.inputs]
            if (max(starts) - min(starts)) * 1000 <= chord.window_ms:
                completed.append(chord)
        return completed

    def _press_mapping(self, mapping: Mapping) -> None:
        if mapping.id in self._active_mappings:
            return
        self.output_manager.press(mapping.output)
        self._active_mappings[mapping.id] = mapping

    def _flush_due_mappings(self, now: float) -> None:
        for input_name, mapping in tuple(self._pending_mappings.items()):
            started = self._pressed_since.get(input_name, now)
            windows = [
                chord.window_ms
                for chord in self._chords
                if (
                    chord.enabled
                    and self._scope_matches(chord)
                    and input_name in chord.inputs
                    and chord.id not in self._fired_chords
                )
            ]
            # Keep the simple mapping pending until every chord candidate
            # that shares this input has expired. Using the shortest window
            # can emit a synthetic simple press while a longer valid chord is
            # still inside its configured recognition window.
            if windows and (now - started) * 1000 < max(windows):
                continue
            self._press_mapping(mapping)
            self._pending_mappings.pop(input_name, None)

    def _release_fallen(self, falling: set[str]) -> None:
        for mapping_id, mapping in tuple(self._active_mappings.items()):
            if mapping.input in falling:
                try:
                    self.output_manager.release(mapping.output)
                finally:
                    self._active_mappings.pop(mapping_id, None)
        for chord_id, chord in tuple(self._active_chords.items()):
            if any(input_name in falling for input_name in chord.inputs):
                try:
                    self.output_manager.release(chord.output)
                finally:
                    self._active_chords.pop(chord_id, None)
        for input_name in falling:
            pending_mapping = self._pending_mappings.pop(input_name) if input_name in self._pending_mappings else None
            if pending_mapping is not None:
                # A quick tap that never completed a chord still gets a
                # complete synthetic edge, rather than being lost.
                self._press_mapping(pending_mapping)
                try:
                    self.output_manager.release(pending_mapping.output)
                finally:
                    self._active_mappings.pop(pending_mapping.id, None)

    def _release_finished_chords(self) -> None:
        for chord_id, chord in tuple(self._active_chords.items()):
            if not set(chord.inputs).issubset(self._pressed):
                self.output_manager.release(chord.output)
                self._active_chords.pop(chord_id, None)

    def _scope_matches(self, item: Mapping | Chord) -> bool:
        configured_game = item.game_id
        return configured_game is None or (self._game_id is not None and configured_game.casefold() == self._game_id)


def _as_output(value: OutputTarget | SyntheticOutput) -> SyntheticOutput:
    return value if isinstance(value, SyntheticOutput) else SyntheticOutput.from_target(value)


def _legacy_mouse_side(code: str) -> bool:
    normalized = code.casefold()
    if normalized in {"left", "left_button", "lmb"}:
        return True
    if normalized in {"right", "right_button", "rmb"}:
        return False
    raise DS5ForgeError(
        ErrorCode.SYNTHETIC_OUTPUT_FAILED,
        "This mouse adapter only supports left/right mapped buttons.",
        fields={"code": code, "allowed": ["left", "right"]},
    )
