"""P4 product services composed around the existing core facade."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..diagnostics.logging import recent_logs
from ..version import __version__
from .diagnostics import DiagnosticCheck, DiagnosticStatus, GuidedDiagnostics
from .remote import RemoteAccessManager
from .support_bundle import build_support_bundle
from .tunnel import CloudflaredManager
from .updates import UpdateMetadata, evaluate_update


class ProductService:
    """Own P4 state that is not controller hardware state.

    This service is deliberately passive: constructing it never starts a
    process, opens a listener, enables remote access or changes the core.
    """

    def __init__(
        self,
        facade: Any,
        *,
        data_dir: str | Path | None = None,
        remote: RemoteAccessManager | None = None,
        tunnel: CloudflaredManager | None = None,
        on_shutdown: Callable[[], None] | None = None,
    ) -> None:
        self.facade = facade
        self.data_dir = Path(data_dir) if data_dir is not None else None
        remote_path = self.data_dir / "remote_sessions.json" if self.data_dir is not None else None
        self.remote = remote or RemoteAccessManager(remote_path)
        self.tunnel = tunnel or CloudflaredManager()
        self._on_shutdown = on_shutdown
        self._last_update: dict[str, Any] | None = None

    def app_info(self) -> dict[str, Any]:
        return {
            "name": "DS5Forge",
            "version": __version__,
            "api_version": 1,
            "transport_scope": "usb_wired_only",
            "platform": {"win32": "windows", "darwin": "macos"}.get(sys.platform, sys.platform),
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "release_channel": "stable",
            "features": {
                "native": True,
                "remap": True,
                "virtual": False,
                "remote_default": False,
                "tunnel_default": False,
            },
        }

    def lifecycle(self) -> dict[str, Any]:
        try:
            snapshot = self.facade.snapshot()
            process_alive = bool(snapshot.health.process_alive)
        except Exception:
            process_alive = False
        if not process_alive:
            state = "core_stopped"
        else:
            state = "application_ready"
        return {"state": state, "core": "ready" if process_alive else "stopped", "pid": None, "message": None}

    def restart_core(self) -> dict[str, Any]:
        self.facade.stop()
        self.facade.start()
        return self.lifecycle()

    def stop_core(self) -> dict[str, Any]:
        """Release core-owned outputs and the tunnel before the shell tears down.

        The tunnel is an outbound child process owned by the core. If it is not
        stopped here, quitting or restarting the core would orphan cloudflared.
        The shutdown callback lets the packaged sidecar terminate itself so the
        one-file bootloader wrapper exits instead of being killed mid-teardown.
        """

        self.facade.stop()
        try:
            self.tunnel.stop()
        finally:
            if self._on_shutdown is not None:
                self._on_shutdown()
        return self.lifecycle()

    def remote_status(self) -> dict[str, Any]:
        return self.remote.status()

    def disable_remote(self) -> dict[str, Any]:
        self.remote.disable()
        # Remote OFF is also a hard stop for any configured tunnel.
        self.tunnel.start(remote_enabled=False)
        return self.remote.status()

    def tunnel_status(self) -> dict[str, Any]:
        return self.tunnel.poll().to_dict()

    def configure_tunnel(self, executable: str | None, config_path: str | None) -> dict[str, Any]:
        if any(value is not None and ("\x00" in value or len(value) > 512) for value in (executable, config_path)):
            raise ValueError("cloudflared executable/config path is invalid")
        stopped = self.tunnel.stop()
        if stopped.status.value == "error":
            raise ValueError(stopped.message or "cloudflared could not be stopped")
        self.tunnel = CloudflaredManager(executable=executable, config_path=config_path)
        return self.tunnel.detect().to_dict()

    def start_tunnel(self) -> dict[str, Any]:
        return self.tunnel.start(remote_enabled=self.remote.has_active_session()).to_dict()

    def stop_tunnel(self) -> dict[str, Any]:
        return self.tunnel.stop().to_dict()

    def check_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            metadata = UpdateMetadata.from_dict(payload)
            result = evaluate_update(__version__, metadata)
        except ValueError as exc:
            result = {"available": False, "status": "invalid_metadata", "message": str(exc)}
        self._last_update = result
        return result

    def guided_diagnostics(self) -> dict[str, Any]:
        state = self._safe_state()
        health = self._safe_health()
        lifecycle = self.lifecycle()
        connection = state.get("connection")
        capabilities = state.get("capabilities") or {}

        def check(
            key: str, status: DiagnosticStatus, summary: str, action: str | None = None, detail: str | None = None
        ) -> DiagnosticCheck:
            return DiagnosticCheck(key, status, summary, action, detail)

        def core_status(key: str, value: Any, *, unavailable: str = "Subsystem is unavailable.") -> DiagnosticCheck:
            if value in {"ready", "connected", "healthy", "online", True}:
                return check(key, DiagnosticStatus.HEALTHY, "The subsystem reported a healthy state.")
            if value in {"waiting", "starting", "reconnecting", "degraded", "stopped"}:
                return check(
                    key,
                    DiagnosticStatus.WARNING,
                    f"Subsystem state is {value}.",
                    "Review the related settings and retry.",
                )
            if value in {"unavailable", None, False}:
                return check(
                    key, DiagnosticStatus.UNAVAILABLE, unavailable, "Connect the controller or start the core."
                )
            if value == "not_applicable":
                return check(
                    key, DiagnosticStatus.NOT_APPLICABLE, "This subsystem is not applicable in the current mode."
                )
            return check(
                key,
                DiagnosticStatus.FAILED,
                f"Subsystem reported {value}.",
                "Export a Support Bundle and inspect the error.",
            )

        providers = {
            "shell": lambda: check("shell", DiagnosticStatus.HEALTHY, "The product shell API is available."),
            "sidecar": lambda: core_status(
                "sidecar", lifecycle.get("core"), unavailable="The Python sidecar is not ready."
            ),
            "api": lambda: core_status("api", "healthy" if health.get("process_alive") else "offline"),
            "websocket": lambda: check(
                "websocket", DiagnosticStatus.HEALTHY, "The versioned WebSocket endpoint is exposed."
            ),
            "usb": lambda: core_status("usb", connection, unavailable="No USB controller is connected."),
            "capabilities": lambda: check(
                "capabilities",
                DiagnosticStatus.HEALTHY if capabilities else DiagnosticStatus.UNAVAILABLE,
                "Controller capabilities are available."
                if capabilities
                else "Capabilities are not available until USB connection.",
            ),
            "haptics": lambda: core_status(
                "haptics",
                (health.get("subsystems") or {}).get("audio"),
                unavailable="Haptics/audio capture is unavailable.",
            ),
            "foreground": lambda: core_status(
                "foreground", (health.get("subsystems") or {}).get("foreground", "not_applicable")
            ),
            "automation": lambda: core_status(
                "automation", (health.get("subsystems") or {}).get("automation", "not_applicable")
            ),
            "synthetic_output": lambda: check(
                "synthetic_output", DiagnosticStatus.HEALTHY, "Teardown/release ownership is present."
            ),
            "update": lambda: check(
                "update",
                DiagnosticStatus.WARNING,
                "No update metadata has been checked in this session."
                if self._last_update is None
                else str(self._last_update.get("status")),
                "Use Check for updates in Settings.",
            ),
            "remote": lambda: check(
                "remote",
                DiagnosticStatus.WARNING if self.remote.enabled else DiagnosticStatus.NOT_APPLICABLE,
                "Remote access is enabled." if self.remote.enabled else "Remote access is OFF by default.",
            ),
            "tunnel": lambda: check(
                "tunnel",
                DiagnosticStatus.NOT_APPLICABLE
                if self.tunnel.snapshot.status.value == "off"
                else DiagnosticStatus.WARNING,
                self.tunnel.snapshot.message or self.tunnel.snapshot.status.value,
            ),
        }
        return GuidedDiagnostics(providers).to_dict()

    def support_bundle(self) -> bytes:
        state = self._safe_state()
        safe_state = {
            key: value
            for key, value in state.items()
            if key not in {"telemetry", "input"}  # keep bundle bounded; diagnostics retains health/capabilities
        }
        entries = {
            "app_info": self.app_info(),
            "lifecycle": self.lifecycle(),
            "health": self._safe_health(),
            "capabilities": state.get("capabilities", {}),
            "state": safe_state,
            "diagnostics": self.guided_diagnostics(),
            "schemas": {"api_version": 1, "api_prefix": "/api/v1"},
            "packaging": {"installer": "nsis", "sidecar": "DS5ForgeCore", "updater": "signed_https"},
            "remote": self.remote_status(),
            "tunnel": self.tunnel_status(),
            "logs_recent": recent_logs(),
        }
        return build_support_bundle(entries)

    def _safe_state(self) -> dict[str, Any]:
        try:
            value = self.facade.state_dict()
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def _safe_health(self) -> dict[str, Any]:
        try:
            value = self.facade.health_dict()
            return value if isinstance(value, dict) else {}
        except Exception:
            return {
                "status": "failed",
                "process_alive": False,
                "controller_available": False,
                "subsystems": {},
                "degraded": ["core"],
            }
