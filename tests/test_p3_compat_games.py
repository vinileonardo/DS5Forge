import asyncio
import copy
import importlib.util
import json
import tempfile
import time
import unittest
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from dualsense_companion.core.config import ConfigRepository, default_controller_profile
from dualsense_companion.core.facade import CoreFacade
from dualsense_companion.core.game_automation import ForegroundWorker, conflict_diagnostics, evaluate_game_rules
from dualsense_companion.core.games_repository import (
    GameRegistryRepository,
    GameRegistryValidationError,
    default_games_config,
    validate_games_config,
)
from dualsense_companion.core.outputs import OutputManager, RemappingEngine
from dualsense_companion.core.virtual_controller import FakeVirtualControllerProvider
from dualsense_companion.domain.errors import DS5ForgeError, ErrorCode
from dualsense_companion.domain.games import (
    Chord,
    CompatibilityMode,
    ForegroundApplication,
    GameDefinition,
    Mapping,
    OutputKind,
    OutputTarget,
    SyntheticOutput,
)
from dualsense_companion.platform.windows.foreground import (
    _configure_kernel32 as configure_foreground_kernel32,
)
from dualsense_companion.platform.windows.foreground import _configure_user32
from dualsense_companion.platform.windows.process_diagnostics import (
    _configure_kernel32 as configure_process_kernel32,
)


class FakeControllerFactory:
    def connect(self):
        raise AssertionError("controller connection is not expected in P3 unit tests")


class FakeMouse:
    def __init__(self, *, fail_release: bool = False):
        self.calls = []
        self.fail_release = fail_release

    def move(self, dx, dy):
        self.calls.append(("move", dx, dy))

    def button(self, left, down):
        self.calls.append(("button", left, down))

    def wheel(self, amount, horizontal=False):
        self.calls.append(("wheel", amount, horizontal))

    def release_all(self):
        self.calls.append(("release_all",))
        if self.fail_release:
            raise RuntimeError("mouse release failed")


class MappedFakeMouse(FakeMouse):
    def button_code(self, code, down):
        self.calls.append(("button_code", str(code), bool(down)))


class FakeKeyboard:
    def __init__(self, *, fail_release_code: str | None = None):
        self.calls = []
        self.fail_release_code = fail_release_code

    def key(self, code, down):
        self.calls.append((str(code), bool(down)))
        if not down and code == self.fail_release_code:
            raise RuntimeError("keyboard release failed")

    def release_all(self):
        self.calls.append(("release_all",))
        if self.fail_release_code is not None:
            raise RuntimeError("keyboard adapter cleanup failed")


class FakeForegroundDetector:
    def __init__(self, observations):
        self.observations = list(observations)
        self.calls = 0

    def current(self):
        self.calls += 1
        if not self.observations:
            return ForegroundApplication.desktop(now=time.time())
        return self.observations.pop(0)


class FailingForegroundDetector:
    def current(self):
        raise PermissionError("access denied")


class FakeProcessInspector:
    def __init__(self, names=None, error=None):
        self.names = names
        self.error = error

    def running_processes(self):
        if self.error:
            raise self.error
        return None if self.names is None else set(self.names)


def make_config_repository(root: Path) -> ConfigRepository:
    return ConfigRepository(
        config_path=root / "config.json",
        bundled_config_path=Path("source/dualsense_companion/resources/default_config.json"),
        bundled_profiles_dir=Path("source/dualsense_companion/resources/profiles"),
        user_profiles_dir=root / "profiles",
    )


def make_facade(root: Path, **kwargs) -> CoreFacade:
    return CoreFacade(
        controller_factory=FakeControllerFactory(),
        mouse_output=kwargs.pop("mouse_output", FakeMouse()),
        config_repository=make_config_repository(root),
        games_repository=GameRegistryRepository(path=root / "games.json"),
        **kwargs,
    )


def foreground(name: str, pid: int, *, path: str | None = None, now: float = 1.0) -> ForegroundApplication:
    return ForegroundApplication(
        available=True,
        pid=pid,
        executable_name=name,
        executable_path=path or f"C:\\Games\\{name}",
        title="A mutable title",
        observed_at=now,
        process_alive=True,
    )


def game(game_id: str, executable: str, *, profile: str = "Default") -> dict:
    return GameDefinition(id=game_id, name=game_id.title(), executables=(executable,), profile=profile).to_dict()


class P3DomainTests(unittest.TestCase):
    def test_matching_is_case_insensitive_and_does_not_use_window_title(self):
        candidate = GameDefinition(id="game", name="Game", executables=("GAME.EXE", "launcher.exe"))
        observed = foreground("game.exe", 42)
        self.assertTrue(candidate.matches(observed).matched)
        self.assertTrue(candidate.matches(foreground("LAUNCHER.EXE", 43)).matched)

        wrong_path = GameDefinition(
            id="game",
            name="Game",
            executables=("game.exe",),
            executable_path="C:\\Other\\game.exe",
        )
        self.assertFalse(wrong_path.matches(observed).matched)
        self.assertIn("path", wrong_path.matches(observed).reason)

    def test_rule_evaluation_explains_all_rules_and_selects_first_match(self):
        match, evaluations = evaluate_game_rules(
            foreground("game.exe", 1),
            (
                GameDefinition(id="first", name="First", executables=("game.exe",)),
                GameDefinition(id="second", name="Second", executables=("game.exe",)),
            ),
        )
        self.assertEqual(match.game_id, "first")
        self.assertEqual([item.action for item in evaluations], ["activate", "none"])
        self.assertTrue(evaluations[0].matched)
        self.assertTrue(evaluations[1].matched)

    def test_foreground_worker_converts_adapter_failure_and_shutdown_is_bounded(self):
        observations = []
        errors = []
        worker = ForegroundWorker(
            FailingForegroundDetector(),
            lambda value, changed: observations.append((value, changed)),
            on_error=errors.append,
            interval=0.01,
        )
        self.assertEqual(worker.interval, 0.5)
        observation = worker.poll_once()
        self.assertFalse(observation.available)
        self.assertFalse(observation.process_alive)
        self.assertEqual(errors[0].code, ErrorCode.FOREGROUND_UNAVAILABLE)
        self.assertEqual(len(observations), 1)

        detector = FakeForegroundDetector([foreground("game.exe", 1)])
        running = ForegroundWorker(detector, lambda _value, _changed: None, interval=0.5)
        running.start()
        running.stop(join_timeout=1.0)
        self.assertFalse(running.alive)

    def test_conflict_diagnostics_are_process_name_evidence_only(self):
        diagnostics = conflict_diagnostics(
            ("steam.exe", "rewasd.exe"),
            FakeProcessInspector({"Steam.EXE"}),
            now=10,
        )
        self.assertEqual(len(diagnostics), 2)
        self.assertEqual(
            diagnostics[0].message, "Steam is running. Steam Input may affect this game depending on its configuration."
        )
        self.assertIn("not proven", diagnostics[0].evidence)
        self.assertFalse(diagnostics[1].running)

        unavailable = conflict_diagnostics(("steam.exe",), FakeProcessInspector(error=RuntimeError("denied")))
        self.assertEqual(unavailable[0].severity, "info")
        self.assertIn("Could not inspect", unavailable[0].message)

        unsupported = conflict_diagnostics(("steam.exe",), FakeProcessInspector(names=None))
        self.assertEqual(unsupported[0].severity, "info")
        self.assertIn("Could not inspect", unsupported[0].message)
        self.assertIn("unavailable", unsupported[0].evidence)


class P3RegistryTests(unittest.TestCase):
    def test_registry_is_strict_atomic_and_recovers_to_safe_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "games.json"
            repository = GameRegistryRepository(path=path)
            initial = repository.load()
            self.assertEqual(initial["schema_version"], 2)
            self.assertTrue(path.exists())

            valid = copy.deepcopy(initial)
            valid["games"] = [game("steam-game", "game.exe")]
            saved = repository.save(valid)
            before = path.read_text(encoding="utf-8")
            self.assertEqual(saved["games"][0]["id"], "steam-game")

            duplicate = copy.deepcopy(saved)
            duplicate["games"].append({**duplicate["games"][0], "id": "STEAM-GAME"})
            with self.assertRaises(GameRegistryValidationError):
                repository.save(duplicate)
            self.assertEqual(path.read_text(encoding="utf-8"), before)

            legacy = copy.deepcopy(saved)
            legacy["schema_version"] = 1
            legacy["games"][0]["executable"] = legacy["games"][0]["executables"][0]
            legacy["games"][0].pop("executables")
            path.write_text(json.dumps(legacy), encoding="utf-8")
            migrated = repository.load()
            self.assertEqual(migrated["schema_version"], 2)
            self.assertEqual(migrated["games"][0]["executables"], ["game.exe"])

            path.write_text("{broken", encoding="utf-8")
            recovered = repository.load()
            self.assertEqual(recovered["games"], [])
            self.assertEqual(repository.last_error.code, ErrorCode.GAME_REGISTRY_LOAD_FAILED)

    def test_registry_validates_multiple_executables_and_exact_path_scope(self):
        document = default_games_config()
        document["games"] = [
            {
                "id": "multi",
                "name": "Multi",
                "executables": ["game.exe", "launcher.exe"],
                "executable_path": None,
                "profile": "Default",
                "compatibility_mode": "native",
                "enabled": True,
            }
        ]
        normalized = validate_games_config(document)
        self.assertEqual(normalized["games"][0]["executables"], ["game.exe", "launcher.exe"])

        duplicate = copy.deepcopy(document)
        duplicate["games"][0]["executables"] = ["game.exe", "GAME.EXE"]
        with self.assertRaises(GameRegistryValidationError):
            validate_games_config(duplicate)

        ambiguous_path = copy.deepcopy(document)
        ambiguous_path["games"][0]["executable_path"] = "C:\\Games\\game.exe"
        with self.assertRaises(GameRegistryValidationError):
            validate_games_config(ambiguous_path)

    def test_registry_rejects_conflicting_mappings_and_ambiguous_chords_before_apply(self):
        document = default_games_config()
        document["games"] = [game("one", "one.exe")]
        document["mappings"] = [
            {
                "id": "one-a",
                "input": "cross",
                "output_kind": "keyboard",
                "output_code": "A",
                "game_id": "one",
                "enabled": True,
                "debounce_ms": 25,
            },
            {
                "id": "one-b",
                "input": "cross",
                "output_kind": "keyboard",
                "output_code": "B",
                "game_id": "one",
                "enabled": True,
                "debounce_ms": 25,
            },
        ]
        with self.assertRaises(GameRegistryValidationError):
            validate_games_config(document)

        document["mappings"] = [
            {
                "id": "global-cross",
                "input": "cross",
                "output_kind": "keyboard",
                "output_code": "A",
                "game_id": None,
                "enabled": True,
                "debounce_ms": 25,
            },
            {
                "id": "scoped-cross",
                "input": "cross",
                "output_kind": "keyboard",
                "output_code": "B",
                "game_id": "one",
                "enabled": True,
                "debounce_ms": 25,
            },
        ]
        document["chords"] = []
        with self.assertRaises(GameRegistryValidationError) as raised:
            validate_games_config(document)
        self.assertEqual(raised.exception.code, ErrorCode.MAPPING_CONFLICT)

        document["mappings"] = []
        chord = {
            "id": "first",
            "inputs": ["l1", "r1"],
            "output_kind": "keyboard",
            "output_code": "ESC",
            "game_id": "one",
            "enabled": True,
            "window_ms": 250,
            "debounce_ms": 25,
        }
        document["chords"] = [chord, {**chord, "id": "second", "inputs": ["r1", "l1"]}]
        with self.assertRaises(GameRegistryValidationError):
            validate_games_config(document)

        document["chords"] = [
            chord,
            {**chord, "id": "subset", "inputs": ["l1", "r1", "cross"]},
        ]
        with self.assertRaises(GameRegistryValidationError) as subset:
            validate_games_config(document)
        self.assertEqual(subset.exception.code, ErrorCode.CHORD_CONFLICT)

    def test_registry_rejects_runtime_unsupported_outputs_and_normalizes_mouse4(self):
        document = default_games_config()
        base_mapping = {
            "id": "mapped-output",
            "input": "cross",
            "output_kind": "mouse",
            "output_code": "Mouse4",
            "game_id": None,
            "enabled": True,
            "debounce_ms": 25,
        }
        document["mappings"] = [base_mapping]
        normalized = validate_games_config(document)
        self.assertEqual(normalized["mappings"][0]["output_code"], "mouse4")

        combo = copy.deepcopy(document)
        combo["mappings"][0]["output_kind"] = "keyboard"
        combo["mappings"][0]["output_code"] = "Ctrl + Shift + s"
        normalized_combo = validate_games_config(combo)
        self.assertEqual(normalized_combo["mappings"][0]["output_code"], "CTRL+SHIFT+S")

        for kind, code in (("mouse", "mouse9"), ("keyboard", "F13"), ("logical", "button-a")):
            invalid = copy.deepcopy(document)
            invalid["mappings"][0]["output_kind"] = kind
            invalid["mappings"][0]["output_code"] = code
            with self.subTest(kind=kind, code=code), self.assertRaises(GameRegistryValidationError):
                validate_games_config(invalid)


class P3OutputTests(unittest.TestCase):
    def test_mouse4_uses_named_mouse_adapter_and_releases_cleanly(self):
        mouse = MappedFakeMouse()
        manager = OutputManager(mouse, keyboard=FakeKeyboard())
        target = OutputTarget(OutputKind.MOUSE, "mouse4")

        manager.press(target)
        manager.release(target)

        self.assertEqual(mouse.calls[:2], [("button_code", "mouse4", True), ("button_code", "mouse4", False)])
        self.assertEqual(manager.held, ())

    def test_shared_synthetic_output_is_released_after_all_owners_leave(self):
        keyboard = FakeKeyboard()
        manager = OutputManager(FakeMouse(), keyboard=keyboard)
        target = OutputTarget(OutputKind.KEYBOARD, "A")

        manager.press(target)
        manager.press(target)
        self.assertEqual(keyboard.calls, [("A", True)])
        manager.release(target)
        self.assertEqual(keyboard.calls, [("A", True)])
        self.assertEqual(manager.held, (SyntheticOutput(OutputKind.KEYBOARD, "A"),))
        manager.release(target)
        self.assertEqual(keyboard.calls, [("A", True), ("A", False)])
        self.assertEqual(manager.held, ())

    def test_release_all_attempts_every_output_and_reports_partial_failures(self):
        mouse = FakeMouse()
        keyboard = FakeKeyboard(fail_release_code="A")
        manager = OutputManager(mouse, keyboard=keyboard)
        manager.press(OutputTarget(OutputKind.KEYBOARD, "A"))
        manager.press(OutputTarget(OutputKind.MOUSE, "left"))

        report = manager.release_all("disconnect")

        self.assertFalse(report.completed)
        self.assertTrue(any("keyboard:a" in item for item in report.failures))
        self.assertIn(("button", True, False), mouse.calls)
        self.assertIn(("release_all",), mouse.calls)
        self.assertIn(("release_all",), keyboard.calls)
        self.assertEqual(manager.held, ())

    def test_chords_take_precedence_simple_mappings_fall_back_on_quick_tap_and_scope_is_honored(self):
        keyboard = FakeKeyboard()
        manager = OutputManager(FakeMouse(), keyboard=keyboard)
        engine = RemappingEngine(
            manager,
            mappings=(Mapping("cross-simple", "cross", OutputTarget(OutputKind.KEYBOARD, "SPACE"), debounce_ms=1),),
            chords=(
                Chord(
                    "cross-l1", ("cross", "l1"), OutputTarget(OutputKind.KEYBOARD, "ESC"), window_ms=100, debounce_ms=1
                ),
            ),
        )

        engine.process({}, now=0)
        engine.process({"cross": True}, now=1)
        self.assertNotIn(("SPACE", True), keyboard.calls)
        engine.process({"cross": True, "l1": True}, now=1.01)
        self.assertIn(("ESC", True), keyboard.calls)
        engine.process({}, now=1.02)
        self.assertIn(("ESC", False), keyboard.calls)

        keyboard.calls.clear()
        engine.process({}, now=2)
        engine.process({"cross": True, "l1": True}, now=3)
        self.assertIn(("ESC", True), keyboard.calls)
        self.assertNotIn(("SPACE", True), keyboard.calls)
        engine.process({}, now=3.01)

        keyboard.calls.clear()
        engine.process({}, now=4)
        engine.process({"cross": True}, now=5)
        engine.process({}, now=5.01)
        self.assertEqual(keyboard.calls, [("SPACE", True), ("SPACE", False)])

        scoped_keyboard = FakeKeyboard()
        scoped_manager = OutputManager(FakeMouse(), keyboard=scoped_keyboard)
        scoped = RemappingEngine(
            scoped_manager,
            mappings=(
                Mapping(
                    "game-cross",
                    "cross",
                    OutputTarget(OutputKind.KEYBOARD, "G"),
                    game_id="game-a",
                    debounce_ms=1,
                ),
            ),
        )
        scoped.process({"cross": True}, now=0)
        scoped.process({}, now=1)
        self.assertEqual(scoped_keyboard.calls, [])
        scoped.set_game_context("GAME-A")
        scoped_keyboard.calls.clear()
        scoped.process({"cross": True}, now=2)
        scoped.process({}, now=3)
        self.assertEqual(scoped_keyboard.calls[:2], [("G", True), ("G", False)])

    def test_simple_mapping_waits_for_longest_overlapping_chord_window(self):
        keyboard = FakeKeyboard()
        engine = RemappingEngine(
            OutputManager(FakeMouse(), keyboard=keyboard),
            mappings=(Mapping("cross-simple", "cross", OutputTarget(OutputKind.KEYBOARD, "SPACE"), debounce_ms=1),),
            chords=(
                Chord(
                    "short",
                    ("cross", "l1"),
                    OutputTarget(OutputKind.KEYBOARD, "ESC"),
                    window_ms=50,
                    debounce_ms=1,
                ),
                Chord(
                    "long",
                    ("cross", "r1"),
                    OutputTarget(OutputKind.KEYBOARD, "ENTER"),
                    window_ms=200,
                    debounce_ms=1,
                ),
            ),
        )

        engine.process({"cross": True}, now=1.0)
        engine.process({"cross": True}, now=1.06)
        self.assertNotIn(("SPACE", True), keyboard.calls)
        engine.process({"cross": True, "r1": True}, now=1.1)
        self.assertIn(("ENTER", True), keyboard.calls)
        self.assertNotIn(("SPACE", True), keyboard.calls)


class P3WindowsSignatureTests(unittest.TestCase):
    @staticmethod
    def _dll(*names: str):
        return SimpleNamespace(**{name: Mock() for name in names})

    def test_foreground_win32_handles_are_declared_pointer_sized(self):
        user32 = self._dll("GetForegroundWindow", "GetWindowThreadProcessId", "GetWindowTextLengthW", "GetWindowTextW")
        kernel32 = self._dll("OpenProcess", "QueryFullProcessImageNameW", "CloseHandle")

        _configure_user32(user32)
        configure_foreground_kernel32(kernel32)

        self.assertIs(user32.GetForegroundWindow.restype, wintypes.HWND)
        self.assertIs(kernel32.OpenProcess.restype, wintypes.HANDLE)

    def test_process_snapshot_handle_is_declared_pointer_sized(self):
        kernel32 = self._dll("CreateToolhelp32Snapshot", "Process32FirstW", "Process32NextW", "CloseHandle")

        configure_process_kernel32(kernel32)

        self.assertIs(kernel32.CreateToolhelp32Snapshot.restype, wintypes.HANDLE)


class P3FacadeTests(unittest.TestCase):
    def test_remap_reports_double_input_risk_while_physical_input_remains_visible(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = make_facade(Path(temp))
            try:
                state = facade.update_compatibility("remap")
                self.assertEqual(state["mode"], "remap")
                self.assertTrue(state["physical_input_visible"])
                self.assertFalse(state["virtual_input_active"])
                self.assertFalse(state["physical_suppression_active"])
                self.assertTrue(state["double_input_risk"])
                self.assertIn("physical controller remains visible", state["reason"])

                native = facade.update_compatibility("native")
                self.assertFalse(native["double_input_risk"])
                self.assertIsNone(native["reason"])
            finally:
                facade.stop()

    def test_virtual_is_unavailable_without_provider_and_native_stays_authoritative(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = make_facade(Path(temp))
            try:
                self.assertEqual(facade.snapshot().compatibility.mode, CompatibilityMode.NATIVE)
                with self.assertRaises(DS5ForgeError) as raised:
                    facade.update_compatibility("virtual")
                self.assertEqual(raised.exception.code, ErrorCode.COMPATIBILITY_UNAVAILABLE)
                self.assertEqual(facade.snapshot().compatibility.mode, CompatibilityMode.NATIVE)
            finally:
                facade.stop()

    def test_fake_virtual_provider_is_capability_gated_and_released(self):
        with tempfile.TemporaryDirectory() as temp:
            provider = FakeVirtualControllerProvider()
            facade = make_facade(Path(temp), virtual_provider=provider)
            try:
                state = facade.update_compatibility("virtual")
                self.assertTrue(state["virtual_input_active"])
                self.assertTrue(state["physical_suppression_active"])
                facade._outputs.press(OutputTarget(OutputKind.LOGICAL, "button-a"))
                report = facade.release_all_synthetic_outputs("test")
                self.assertTrue(report["completed"])
                self.assertIn(("button", "button-a", True), provider.events)
                self.assertTrue(provider.started)
                facade.update_compatibility("native")
                self.assertFalse(facade.snapshot().compatibility.virtual_input_active)
                self.assertFalse(provider.started)
            finally:
                facade.stop()

    def test_automation_covers_restore_default_keep_a_to_b_and_manual_override(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = make_facade(Path(temp))
            try:
                manual = default_controller_profile("Manual")
                facade.config_repository.save_controller_profile("Manual", manual)
                facade.apply_controller_profile(manual, name="Manual")
                facade.add_game(game("a", "a.exe"))
                facade.add_game(game("b", "b.exe"))
                facade.update_automation({"enabled": True})
                a = foreground("a.exe", 10)
                b = foreground("b.exe", 11, now=2)
                desktop = ForegroundApplication.desktop(now=3)

                facade._on_foreground_observation(a, True)
                self.assertEqual(facade.snapshot().automation.active_game_id, "a")
                self.assertEqual(facade.snapshot().automation.previous_profile, "Manual")
                facade._on_foreground_observation(b, True)
                self.assertEqual(facade.snapshot().automation.active_game_id, "b")
                facade._on_foreground_observation(desktop, True)
                self.assertEqual(facade.snapshot().active_profile, "Manual")

                facade.update_automation({"exit_policy": "apply_default"})
                facade.apply_controller_profile(default_controller_profile("Manual2"), name="Manual2")
                facade._on_foreground_observation(a, True)
                facade._on_foreground_observation(desktop, True)
                self.assertEqual(facade.snapshot().active_profile, "Default")

                facade.update_automation({"exit_policy": "keep_current"})
                facade.apply_controller_profile(default_controller_profile("Manual3"), name="Manual3")
                facade._on_foreground_observation(a, True)
                self.assertEqual(facade.snapshot().automation.active_game_id, "a")
                facade._on_foreground_observation(desktop, True)
                self.assertEqual(facade.snapshot().active_profile, "Default")

                facade._on_foreground_observation(a, True)
                facade.apply_controller_profile(default_controller_profile("ManualOverride"), name="ManualOverride")
                self.assertTrue(facade.snapshot().automation.manual_override)
                facade._on_foreground_observation(a, False)
                self.assertEqual(facade.snapshot().active_profile, "ManualOverride")
                facade._on_foreground_observation(foreground("a.exe", 12, now=4), True)
                self.assertEqual(facade.snapshot().active_profile, "Default")
                self.assertFalse(facade.snapshot().automation.manual_override)
            finally:
                facade.stop()

    def test_add_game_returns_the_normalized_persisted_id(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = make_facade(Path(temp))
            try:
                candidate = game("normalized", "game.exe")
                candidate["id"] = " normalized "

                saved = facade.add_game(candidate)

                self.assertEqual(saved["id"], "normalized")
                self.assertEqual(facade.games()[0]["id"], "normalized")
            finally:
                facade.stop()

    def test_failed_game_transition_restores_preserved_exit_state(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = make_facade(Path(temp))
            try:
                manual = default_controller_profile("Manual")
                facade.config_repository.save_controller_profile("Manual", manual)
                facade.apply_controller_profile(manual, name="Manual")

                first = game("first", "first.exe")
                first["compatibility_mode"] = "remap"
                second = game("second", "second.exe", profile="MissingProfile")
                facade.add_game(first)
                facade.add_game(second)
                facade.update_automation({"enabled": True})

                facade._on_foreground_observation(foreground("first.exe", 10), True)
                self.assertEqual(facade.snapshot().compatibility.mode, CompatibilityMode.REMAP)
                self.assertEqual(facade.snapshot().active_profile, "Default")

                facade._on_foreground_observation(foreground("second.exe", 11, now=2), True)

                snapshot = facade.snapshot()
                self.assertEqual(snapshot.compatibility.mode, CompatibilityMode.NATIVE)
                self.assertEqual(snapshot.active_profile, "Manual")
                self.assertIsNone(snapshot.automation.active_game_id)
                self.assertIsNone(snapshot.automation.previous_profile)
                self.assertIsNone(snapshot.automation.previous_compatibility_mode)
                self.assertEqual(snapshot.automation.status, "error")

                facade._on_foreground_observation(ForegroundApplication.desktop(now=3), True)
                self.assertEqual(facade.snapshot().active_profile, "Manual")
                self.assertEqual(facade.snapshot().compatibility.mode, CompatibilityMode.NATIVE)
            finally:
                facade.stop()

    def test_enabling_automation_evaluates_the_existing_foreground_context(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = make_facade(Path(temp))
            try:
                facade.add_game(game("existing", "existing.exe"))
                facade._on_foreground_observation(foreground("existing.exe", 12), True)
                self.assertIsNone(facade.snapshot().automation.active_game_id)
                facade.update_automation({"enabled": True})
                self.assertEqual(facade.snapshot().automation.active_game_id, "existing")
            finally:
                facade.stop()

    def test_api_exposes_p3_contracts_and_rejects_virtual_without_mutation(self):
        if not all(importlib.util.find_spec(name) for name in ("fastapi", "httpx", "pydantic")):
            self.skipTest("FastAPI/httpx/pydantic are optional")
        import httpx

        from dualsense_companion.api.http import create_app

        async def exercise():
            with tempfile.TemporaryDirectory() as temp:
                facade = make_facade(Path(temp))
                try:
                    app = create_app(facade)
                    transport = httpx.ASGITransport(app=app)
                    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                        self.assertEqual((await client.get("/api/v1/games")).status_code, 200)
                        missing = await client.get("/api/v1/games/missing")
                        self.assertEqual(missing.status_code, 404)
                        self.assertEqual(missing.json()["error"]["code"], "game.not_found")
                        created = await client.post(
                            "/api/v1/games",
                            json={"id": "api-game", "name": "API Game", "executables": ["game.exe", "launcher.exe"]},
                        )
                        self.assertEqual(created.status_code, 200)
                        self.assertEqual((await client.get("/api/v1/foreground")).status_code, 200)
                        self.assertEqual(
                            (await client.put("/api/v1/automation", json={"enabled": True})).status_code, 200
                        )
                        virtual = await client.put("/api/v1/compatibility", json={"mode": "virtual"})
                        self.assertEqual(virtual.status_code, 422)
                        self.assertEqual(virtual.json()["error"]["code"], "compatibility.unavailable")
                        self.assertEqual((await client.get("/api/v1/compatibility")).json()["mode"], "native")
                        state = await client.get("/api/v1/state")
                        self.assertIn("automation", state.json())
                        self.assertIn("synthetic_outputs", state.json())
                        invalid = await client.put(
                            "/api/v1/mappings",
                            json={
                                "mappings": [
                                    {
                                        "id": "one",
                                        "input": "cross",
                                        "output_kind": "keyboard",
                                        "output_code": "A",
                                        "game_id": None,
                                        "enabled": True,
                                        "debounce_ms": 25,
                                    },
                                    {
                                        "id": "two",
                                        "input": "cross",
                                        "output_kind": "keyboard",
                                        "output_code": "B",
                                        "game_id": None,
                                        "enabled": True,
                                        "debounce_ms": 25,
                                    },
                                ]
                            },
                        )
                        self.assertEqual(invalid.status_code, 422)
                        logical = await client.put(
                            "/api/v1/mappings",
                            json={
                                "mappings": [
                                    {
                                        "id": "logical-output",
                                        "input": "cross",
                                        "output_kind": "logical",
                                        "output_code": "button-a",
                                        "game_id": None,
                                        "enabled": True,
                                        "debounce_ms": 25,
                                    }
                                ]
                            },
                        )
                        self.assertEqual(logical.status_code, 422)
                        self.assertEqual(logical.json()["error"]["code"], "api.validation")
                finally:
                    facade.stop()

        asyncio.run(exercise())

    def test_realtime_events_include_foreground_detection_and_unknown_events_remain_nonfatal(self):
        with tempfile.TemporaryDirectory() as temp:
            facade = make_facade(Path(temp))
            subscription = facade.subscribe()
            try:
                facade.add_game(game("a", "a.exe"))
                facade.update_automation({"enabled": True})
                facade._on_foreground_observation(foreground("a.exe", 7), True)
                events = []
                while True:
                    try:
                        events.append(subscription.get_nowait().type)
                    except Exception:
                        break
                self.assertIn("game.foreground_changed", events)
                self.assertIn("game.detected", events)
                self.assertIn("game.activated", events)
            finally:
                facade.unsubscribe(subscription)
                facade.stop()


if __name__ == "__main__":
    unittest.main()
