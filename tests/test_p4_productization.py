from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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

    def test_release_workflow_uses_tauri_v2_nsis_artifact(self) -> None:
        workflow = (ROOT / ".github/workflows/windows-release.yml").read_text(encoding="utf-8")
        installer = (ROOT / "scripts/build_installer.py").read_text(encoding="utf-8")
        self.assertIn('"createUpdaterArtifacts": True', installer)
        self.assertIn('-Filter "*-setup.exe"', workflow)
        self.assertNotIn("*.nsis.zip", workflow)

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
