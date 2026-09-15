from __future__ import annotations

import io
import json
import runpy
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from dualsense_companion.core.diagnostics import DiagnosticStatus, GuidedDiagnostics
from dualsense_companion.core.lifecycle import CoreSupervisor, LifecycleState, SupervisorConfig, sidecar_command
from dualsense_companion.core.product import ProductService
from dualsense_companion.core.remote import SESSION_COOKIE, RemoteAccessManager, is_loopback_host
from dualsense_companion.core.support_bundle import build_support_bundle, sanitize
from dualsense_companion.core.tunnel import CloudflaredManager, TunnelStatus
from dualsense_companion.core.updates import UpdateMetadata, evaluate_update
from dualsense_companion.diagnostics.logging import configure_logging, get_logger, recent_logs

ROOT = Path(__file__).resolve().parents[1]


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class FakeProcess:
    pid = 123

    def __init__(self, alive: bool = True) -> None:
        self.alive = alive
        self.terminated = False
        self.killed = False

    def is_alive(self) -> bool:
        return self.alive

    def terminate(self) -> None:
        self.terminated = True
        self.alive = False

    def kill(self) -> None:
        self.killed = True
        self.alive = False

    def wait(self, timeout: float) -> bool:
        return not self.alive


class FakeFacade:
    def __init__(self, alive: bool = True) -> None:
        self.alive = alive
        self.stop_count = 0
        self.start_count = 0

    def stop(self) -> None:
        self.stop_count += 1
        self.alive = False

    def start(self) -> None:
        self.start_count += 1
        self.alive = True

    def snapshot(self) -> Any:
        return SimpleNamespace(health=SimpleNamespace(process_alive=self.alive))

    def health_dict(self) -> dict[str, Any]:
        return {"process_alive": self.alive}

    def state_dict(self) -> dict[str, Any]:
        return {}


class FakeTunnel:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.stop_count = 0

    def stop(self, *_args: Any, **_kwargs: Any) -> Any:
        self.stop_count += 1
        if self.fail:
            raise RuntimeError("tunnel stop failed")
        return SimpleNamespace(status=TunnelStatus.STOPPED)


class P4ProductizationTests(unittest.TestCase):
    def test_lifecycle_reaches_application_ready_after_bounded_health_poll(self) -> None:
        clock = FakeClock()
        process = FakeProcess()
        calls = iter(({}, {"status": "waiting_for_controller", "health": {"process_alive": True}}))
        supervisor = CoreSupervisor(
            lambda: process,
            lambda: next(calls),
            config=SupervisorConfig(startup_timeout=2, poll_interval=0.5),
            clock=clock,
            sleeper=clock.sleep,
        )
        snapshot = supervisor.start()
        self.assertEqual(snapshot.state, LifecycleState.APPLICATION_READY)
        self.assertEqual(process.pid, snapshot.pid)
        self.assertEqual(supervisor.stop().state, LifecycleState.CORE_STOPPED)

    def test_lifecycle_timeout_and_restart_limit_are_explicit(self) -> None:
        clock = FakeClock()
        process = FakeProcess()
        supervisor = CoreSupervisor(
            lambda: process,
            lambda: {"status": "starting"},
            config=SupervisorConfig(startup_timeout=1, poll_interval=0.5, max_restarts=0),
            clock=clock,
            sleeper=clock.sleep,
        )
        self.assertEqual(supervisor.start().state, LifecycleState.CORE_TIMEOUT)
        self.assertTrue(process.terminated)
        self.assertEqual(supervisor.restart().state, LifecycleState.CORE_START_FAILED)

    def test_restart_does_not_replace_a_child_that_failed_to_shutdown(self) -> None:
        clock = FakeClock()
        process = FakeProcess()
        process.wait = lambda _timeout: False
        supervisor = CoreSupervisor(
            lambda: process,
            lambda: {"status": "starting"},
            config=SupervisorConfig(startup_timeout=1, shutdown_timeout=0.1, max_restarts=2),
            clock=clock,
            sleeper=clock.sleep,
        )
        supervisor.process = process
        supervisor.snapshot = supervisor.snapshot.__class__(LifecycleState.APPLICATION_READY, pid=process.pid)
        snapshot = supervisor.restart()
        self.assertEqual(snapshot.state, LifecycleState.SHUTDOWN_TIMEOUT)
        self.assertIs(supervisor.process, process)

    def test_sidecar_command_rejects_external_bind(self) -> None:
        self.assertEqual(sidecar_command("core"), ["core", "--headless", "--host", "127.0.0.1", "--port", "8765"])
        with self.assertRaises(ValueError):
            sidecar_command("core", host="0.0.0.0")

    def test_remote_pairing_persists_only_hash_and_requires_origin_cookie(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "remote.json"
            manager = RemoteAccessManager(path)
            challenge = manager.start_pairing()
            session, token = manager.complete_pairing(challenge.pairing_id, challenge.code, "https://remote.example")
            persisted = path.read_text(encoding="utf-8")
            self.assertNotIn(challenge.code, persisted)
            self.assertNotIn(token, persisted)
            self.assertTrue(manager.authenticate(token, "https://remote.example"))
            self.assertEqual(manager.origin_for_host("remote.example"), "https://remote.example")
            self.assertEqual(manager.origin_for_host("remote.example:443"), "https://remote.example")
            self.assertIsNone(manager.origin_for_host("evil.example"))
            self.assertFalse(manager.authenticate(token, "https://other.example"))
            self.assertIn(f"{SESSION_COOKIE}=", manager.cookie_header(token))
            self.assertIn("HttpOnly", manager.cookie_header(token))
            self.assertIn("Secure", manager.cookie_header(token))
            self.assertTrue(manager.revoke(session.session_id))
            self.assertFalse(manager.authenticate(token, "https://remote.example"))
            manager.disable()
            self.assertFalse(manager.status()["enabled"])

    def test_pairing_origin_hint_is_enforced_and_status_is_explicit(self) -> None:
        manager = RemoteAccessManager()
        challenge = manager.start_pairing(origin_hint="https://remote.example")
        with self.assertRaises(ValueError):
            manager.complete_pairing(challenge.pairing_id, challenge.code, "https://other.example")
        self.assertFalse(manager.enabled)

    def test_loopback_host_classification(self) -> None:
        for value in ("127.0.0.1", "127.0.0.1:8765", "localhost", "localhost:8765", "::1", "[::1]", "[::1]:8765"):
            self.assertTrue(is_loopback_host(value), value)
        for value in ("remote.example", "remote.example:443", "evil.example", "0.0.0.0", "", None, "[::1"):
            self.assertFalse(is_loopback_host(value), value)

    def test_remote_origin_rejects_path_and_non_https(self) -> None:
        manager = RemoteAccessManager()
        challenge = manager.start_pairing()
        with self.assertRaises(ValueError):
            manager.complete_pairing(challenge.pairing_id, challenge.code, "http://remote.example")
        with self.assertRaises(ValueError):
            manager.start_pairing(origin_hint="https://remote.example/path")
        self.assertEqual(
            manager.start_pairing(origin_hint="https://remote.example:443").origin_hint,
            "https://remote.example",
        )

    def test_support_bundle_is_bounded_and_sanitized(self) -> None:
        value = sanitize({"token": "secret-token", "paths": ["/users/leo/private.log"], "nested": {"cookie": "abc"}})
        self.assertEqual(value["token"], "[REDACTED]")
        self.assertEqual(value["nested"]["cookie"], "[REDACTED]")
        self.assertEqual(value["paths"], "[REDACTED]")
        archive = build_support_bundle({"../unsafe/name": {"password": "hidden"}, "logs": "x" * 200_000})
        with zipfile.ZipFile(BytesIO(archive)) as bundle:
            names = bundle.namelist()
            self.assertTrue(all(".." not in name and "/" not in name for name in names))
            self.assertIn("README.txt", names)
            joined = b"".join(bundle.read(name) for name in names)
            self.assertNotIn(b"hidden", joined)

    def test_support_bundle_redacts_free_text_machine_paths(self) -> None:
        redacted = sanitize({"message": "failed to read C:\\Users\\leo\\private\\remote.json"})
        serialized = json.dumps(redacted)
        self.assertNotIn("leo", serialized)
        self.assertNotIn("private", serialized)
        self.assertIn("[REDACTED]", serialized)

        posix = sanitize({"note": "see /home/leo/secret.txt"})
        self.assertNotIn("leo", json.dumps(posix))

        unc = sanitize({"detail": r"opened \\server\share\private.log"})
        self.assertNotIn("private.log", json.dumps(unc))

        spaced = sanitize({"message": r"cannot open C:\Users\First Last\AppData\Local\log.txt"})
        self.assertNotIn("First Last", json.dumps(spaced))
        self.assertNotIn("AppData", json.dumps(spaced))

        # HTTPS origins and URLs must not be mistaken for machine paths.
        self.assertEqual(
            sanitize({"origin": "https://remote.example/api/v1"})["origin"],
            "https://remote.example/api/v1",
        )
        self.assertEqual(
            sanitize({"installer_url": "https://example.test/update.exe"})["installer_url"],
            "https://example.test/update.exe",
        )

    def test_guided_diagnostics_captures_provider_failures_without_exception_payload(self) -> None:
        diagnostics = GuidedDiagnostics(
            {
                "api": lambda: {"status": "healthy", "summary": "ok"},
                "usb": lambda: (_ for _ in ()).throw(RuntimeError("secret-token")),
            }
        ).to_dict()
        checks = {item["key"]: item for item in diagnostics["checks"]}
        self.assertEqual(checks["api"]["status"], DiagnosticStatus.HEALTHY.value)
        self.assertEqual(checks["usb"]["status"], DiagnosticStatus.FAILED.value)
        self.assertNotIn("secret-token", json.dumps(diagnostics))

    def test_recent_logs_redact_labeled_credentials(self) -> None:
        stream = io.StringIO()
        configure_logging(stream=stream)
        get_logger("p4-test").warning("token=%s bearer abc cookie=xyz", "secret-token")
        self.assertNotIn("secret-token", stream.getvalue())
        self.assertNotIn("secret-token", json.dumps(recent_logs()))

    def test_tunnel_is_opt_in_and_missing_executable_is_not_downloaded(self) -> None:
        manager = CloudflaredManager(executable="cloudflared", config_path="/no/such/config.yml")
        self.assertIn(manager.detect().status, {TunnelStatus.MISSING, TunnelStatus.CONFIG_INVALID})
        self.assertEqual(manager.start(remote_enabled=False).status, TunnelStatus.OFF)

    def test_update_rejects_invalid_and_downgrade_metadata(self) -> None:
        with self.assertRaises(ValueError):
            UpdateMetadata.from_dict({"version": "0.5.0", "signature": "x", "installer_url": "http://bad"})
        metadata = UpdateMetadata.from_dict(
            {"version": "0.3.0", "signature": "signed", "installer_url": "https://example.test/update.exe"}
        )
        result = evaluate_update("0.4.0", metadata)
        self.assertEqual(result["status"], "rejected_downgrade")

    def test_update_uses_semver_prerelease_precedence(self) -> None:
        def metadata(version: str) -> UpdateMetadata:
            return UpdateMetadata.from_dict(
                {"version": version, "signature": "signed", "installer_url": "https://example.test/update.exe"}
            )

        self.assertEqual(evaluate_update("0.4.0-rc.1", metadata("0.4.0-rc.2"))["status"], "available")
        self.assertEqual(evaluate_update("0.4.0-rc.2", metadata("0.4.0"))["status"], "available")
        self.assertEqual(evaluate_update("0.4.0", metadata("0.4.0-rc.2"))["status"], "rejected_downgrade")
        self.assertEqual(evaluate_update("0.4.0-rc.2", metadata("0.4.0-rc.10"))["status"], "available")
        self.assertEqual(evaluate_update("0.4.0+build.1", metadata("0.4.0+build.2"))["status"], "up_to_date")

    def test_stop_core_releases_outputs_stops_tunnel_and_signals_shutdown(self) -> None:
        facade = FakeFacade()
        tunnel = FakeTunnel()
        shutdowns: list[str] = []
        product = ProductService(facade, tunnel=tunnel, on_shutdown=lambda: shutdowns.append("stop"))

        status = product.stop_core()

        self.assertEqual(facade.stop_count, 1)
        self.assertEqual(tunnel.stop_count, 1)
        self.assertEqual(shutdowns, ["stop"])
        self.assertEqual(status["state"], "core_stopped")

    def test_stop_core_still_signals_shutdown_when_tunnel_stop_fails(self) -> None:
        facade = FakeFacade()
        tunnel = FakeTunnel(fail=True)
        shutdowns: list[str] = []
        product = ProductService(facade, tunnel=tunnel, on_shutdown=lambda: shutdowns.append("stop"))

        with self.assertRaises(RuntimeError):
            product.stop_core()

        # Hardware must be released and the sidecar must still be asked to exit.
        self.assertEqual(facade.stop_count, 1)
        self.assertEqual(shutdowns, ["stop"])

    def test_restart_core_does_not_request_process_exit(self) -> None:
        facade = FakeFacade()
        tunnel = FakeTunnel()
        shutdowns: list[str] = []
        product = ProductService(facade, tunnel=tunnel, on_shutdown=lambda: shutdowns.append("stop"))

        status = product.restart_core()

        self.assertEqual(facade.stop_count, 1)
        self.assertEqual(facade.start_count, 1)
        self.assertEqual(tunnel.stop_count, 0)
        self.assertEqual(shutdowns, [])
        self.assertEqual(status["state"], "application_ready")


class TestTauriReleaseContract(unittest.TestCase):
    """Guards config/dependency regressions that only native Rust compilation exposes."""

    def test_tauri_cargo_manifest_declares_generate_context_dependency(self) -> None:
        manifest = (ROOT / "frontend/src-tauri/Cargo.toml").read_text(encoding="utf-8")
        # tauri::generate_context! expands to code that references serde_json in
        # the crate root; omitting the direct dependency breaks native cargo check.
        self.assertRegex(manifest, r'(?m)^serde_json\s*=\s*"1"')

    def test_cargo_lock_resolves_desktop_plugins(self) -> None:
        lock = (ROOT / "frontend/src-tauri/Cargo.lock").read_text(encoding="utf-8")
        for plugin in (
            "tauri-plugin-autostart",
            "tauri-plugin-process",
            "tauri-plugin-shell",
            "tauri-plugin-single-instance",
            "tauri-plugin-updater",
        ):
            self.assertIn(f'name = "{plugin}"', lock)

    def test_tauri_updater_plugin_has_deserializable_config(self) -> None:
        config = json.loads((ROOT / "frontend/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
        updater = config["plugins"]["updater"]
        # tauri-plugin-updater declares `pubkey: String` with no serde default.
        # Without this key the app panics while initializing plugins at startup.
        self.assertIn("pubkey", updater)
        self.assertIsInstance(updater["pubkey"], str)
        self.assertIsInstance(updater.get("endpoints", []), list)

    def test_tauri_rust_sidecar_uses_external_bin_basename(self) -> None:
        config = json.loads((ROOT / "frontend/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
        self.assertEqual(config["bundle"]["externalBin"], ["binaries/ds5forge-core"])
        rust = (ROOT / "frontend/src-tauri/src/lib.rs").read_text(encoding="utf-8")
        self.assertIn('.sidecar("ds5forge-core")', rust)
        self.assertNotIn('.sidecar("binaries/ds5forge-core")', rust)

    def test_sidecar_entrypoint_preserves_shell_bind_arguments(self) -> None:
        entrypoint = runpy.run_path(str(ROOT / "source/run_sidecar.py"))
        self.assertEqual(
            entrypoint["sidecar_argv"](["--headless", "--host", "127.0.0.1", "--port", "18765"]),
            ["--headless", "--host", "127.0.0.1", "--port", "18765"],
        )

    def test_packaged_core_declares_and_collects_websocket_runtime(self) -> None:
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        requirements = (ROOT / "source/requirements.txt").read_text(encoding="utf-8")
        spec = (ROOT / "source/build.spec").read_text(encoding="utf-8")
        self.assertIn('"websockets>=13,<16"', pyproject)
        self.assertIn("websockets>=13,<16", requirements)
        self.assertIn('"websockets"', spec)
        self.assertIn('("customtkinter", "fastapi", "uvicorn", "websockets")', spec)

    def test_windows_gui_subsystem_attribute_is_on_binary_entrypoint(self) -> None:
        main = (ROOT / "frontend/src-tauri/src/main.rs").read_text(encoding="utf-8")
        library = (ROOT / "frontend/src-tauri/src/lib.rs").read_text(encoding="utf-8")
        attribute = '#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]'
        self.assertIn(attribute, main)
        self.assertNotIn(attribute, library)

    def test_pe_subsystem_verifier_distinguishes_gui_and_console(self) -> None:
        verifier = runpy.run_path(str(ROOT / "scripts/verify_windows_pe_subsystem.py"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def write_pe(path: Path, subsystem: int) -> None:
                payload = bytearray(0x120)
                payload[:2] = b"MZ"
                payload[0x3C:0x40] = (0x80).to_bytes(4, "little")
                payload[0x80:0x84] = b"PE\0\0"
                optional_header = 0x80 + 24
                payload[optional_header : optional_header + 2] = (0x20B).to_bytes(2, "little")
                payload[optional_header + 68 : optional_header + 70] = subsystem.to_bytes(2, "little")
                path.write_bytes(payload)

            gui = root / "gui.exe"
            console = root / "console.exe"
            write_pe(gui, verifier["IMAGE_SUBSYSTEM_WINDOWS_GUI"])
            write_pe(console, verifier["IMAGE_SUBSYSTEM_WINDOWS_CUI"])
            self.assertEqual(verifier["read_pe_subsystem"](gui), verifier["IMAGE_SUBSYSTEM_WINDOWS_GUI"])
            self.assertEqual(
                verifier["read_pe_subsystem"](console),
                verifier["IMAGE_SUBSYSTEM_WINDOWS_CUI"],
            )

    def test_release_workflow_uses_tauri_v2_nsis_artifact(self) -> None:
        workflow = (ROOT / ".github/workflows/windows-release.yml").read_text(encoding="utf-8")
        ci_workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        installer = (ROOT / "scripts/build_installer.py").read_text(encoding="utf-8")
        self.assertIn('"createUpdaterArtifacts": True', installer)
        self.assertIn('-Filter "*-setup.exe"', workflow)
        self.assertNotIn("*.nsis.zip", workflow)
        self.assertIn("verify_windows_pe_subsystem.py", workflow)
        self.assertIn("verify_windows_pe_subsystem.py", ci_workflow)
        self.assertIn("smoke_packaged_core.py", workflow)
        self.assertGreaterEqual(ci_workflow.count("smoke_packaged_core.py"), 2)

    def test_release_build_uses_separate_rc_and_stable_update_channels(self) -> None:
        installer = runpy.run_path(str(ROOT / "scripts/build_installer.py"))
        self.assertEqual(
            installer["updater_endpoint"]("0.4.0-rc.1"),
            "https://github.com/vinileonardo/DS5Forge/releases/download/update-rc/latest.json",
        )
        self.assertEqual(
            installer["updater_endpoint"]("0.4.0"),
            "https://github.com/vinileonardo/DS5Forge/releases/latest/download/latest.json",
        )

    def test_release_build_resolves_windows_npm_cmd_for_python_subprocess(self) -> None:
        installer = runpy.run_path(str(ROOT / "scripts/build_installer.py"))
        resolver = installer["resolve_npm_executable"]
        shutil_module = resolver.__globals__["shutil"]

        def fake_which(candidate: str) -> str | None:
            return r"C:\\Program Files\\nodejs\\npm.cmd" if candidate == "npm.cmd" else None

        with patch.object(shutil_module, "which", side_effect=fake_which):
            self.assertEqual(
                resolver(platform_name="nt"),
                r"C:\\Program Files\\nodejs\\npm.cmd",
            )

    def test_release_workflow_publishes_versioned_release_and_refreshes_rc_channel(self) -> None:
        workflow = (ROOT / ".github/workflows/windows-release.yml").read_text(encoding="utf-8")
        publisher = runpy.run_path(str(ROOT / "scripts/publish_github_release.py"))
        self.assertIn("permissions:\n  contents: write", workflow)
        self.assertIn("Publish GitHub Release and updater channel", workflow)
        self.assertIn("python scripts/publish_github_release.py", workflow)
        self.assertEqual(publisher["RC_CHANNEL_TAG"], "update-rc")
        self.assertTrue(publisher["is_prerelease"]("v0.4.0-rc.1"))
        self.assertFalse(publisher["is_prerelease"]("v0.4.0"))
        with self.assertRaises(ValueError):
            publisher["is_prerelease"]("0.4.0-rc.1")

    def test_release_publisher_requires_one_complete_nsis_asset_set(self) -> None:
        publisher = runpy.run_path(str(ROOT / "scripts/publish_github_release.py"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "bundle"
            bundle.mkdir()
            installer = bundle / "DS5Forge_0.4.0-rc.1_x64-setup.exe"
            core = root / "DS5ForgeCore.exe"
            for path in (
                installer,
                Path(f"{installer}.sig"),
                bundle / "latest.json",
                bundle / "SHA256SUMS.txt",
                core,
            ):
                path.write_text("fixture", encoding="utf-8")
            assets = publisher["release_assets"](bundle, core)
            self.assertEqual(assets[0], installer)
            self.assertEqual(len(assets), 5)
            (bundle / "duplicate-setup.exe").write_text("fixture", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                publisher["release_assets"](bundle, core)

    def test_release_publisher_marks_rc_and_stable_releases_correctly(self) -> None:
        publisher = runpy.run_path(str(ROOT / "scripts/publish_github_release.py"))
        commands: list[list[str]] = []

        def fake_run_gh(args: list[str], *, capture: bool = False, check: bool = True) -> Any:
            commands.append(args)
            return SimpleNamespace(returncode=1 if args[:2] == ["release", "view"] else 0, stderr="")

        publish = publisher["publish_versioned_release"]
        publish.__globals__["run_gh"] = fake_run_gh
        assets = [Path("DS5Forge-setup.exe")]
        publish("v0.4.0-rc.1", "owner/repo", assets)
        rc_create = next(command for command in commands if command[:2] == ["release", "create"])
        self.assertIn("--prerelease", rc_create)
        self.assertIn("--latest=false", rc_create)

        commands.clear()
        publish("v0.4.0", "owner/repo", assets)
        stable_create = next(command for command in commands if command[:2] == ["release", "create"])
        self.assertIn("--latest", stable_create)
        self.assertNotIn("--prerelease", stable_create)

    def test_tauri_capabilities_stay_minimal(self) -> None:
        capabilities = json.loads((ROOT / "frontend/src-tauri/capabilities/default.json").read_text(encoding="utf-8"))
        permissions = capabilities["permissions"]
        self.assertIn("core:default", permissions)
        identifiers = [item if isinstance(item, str) else item.get("identifier") for item in permissions]
        self.assertNotIn("shell:default", identifiers)
        self.assertNotIn("shell:allow-open", identifiers)
        self.assertNotIn("fs:default", identifiers)
        allowed_execute = next(item for item in permissions if isinstance(item, dict))
        self.assertEqual(allowed_execute["identifier"], "shell:allow-execute")
        self.assertTrue(allowed_execute["allow"][0]["sidecar"])
        self.assertEqual(
            allowed_execute["allow"][0]["args"],
            ["--headless", "--host", "127.0.0.1", "--port", "8765"],
        )
