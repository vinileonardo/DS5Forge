"""Explicitly configured, outbound-only cloudflared process boundary."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class TunnelStatus(StrEnum):
    OFF = "off"
    NOT_CONFIGURED = "not_configured"
    MISSING = "missing"
    CONFIG_INVALID = "config_invalid"
    STARTING = "starting"
    ONLINE = "online"
    DEGRADED = "degraded"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class TunnelSnapshot:
    status: TunnelStatus
    executable: str | None = None
    config: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "executable": self.executable,
            "config": self.config,
            "message": self.message,
        }


class CloudflaredManager:
    def __init__(self, *, executable: str | None = None, config_path: str | Path | None = None) -> None:
        self.executable = executable
        self.config_path = Path(config_path) if config_path else None
        self.process: subprocess.Popen[Any] | None = None
        self.snapshot = TunnelSnapshot(TunnelStatus.OFF)

    def detect(self) -> TunnelSnapshot:
        if not self.executable:
            self.snapshot = TunnelSnapshot(TunnelStatus.NOT_CONFIGURED, message="cloudflared is not configured")
            return self.snapshot
        resolved = shutil.which(self.executable) or (self.executable if Path(self.executable).is_file() else None)
        if not resolved:
            self.snapshot = TunnelSnapshot(
                TunnelStatus.MISSING, message="configured cloudflared executable was not found"
            )
            return self.snapshot
        if self.config_path is None:
            self.snapshot = TunnelSnapshot(
                TunnelStatus.NOT_CONFIGURED, executable=resolved, message="tunnel config is not configured"
            )
            return self.snapshot
        try:
            self._validate_config(self.config_path)
        except (OSError, ValueError) as exc:
            self.snapshot = TunnelSnapshot(
                TunnelStatus.CONFIG_INVALID,
                executable=resolved,
                config=self._safe_path(self.config_path),
                message=str(exc),
            )
            return self.snapshot
        self.snapshot = TunnelSnapshot(
            TunnelStatus.STOPPED, executable=resolved, config=self._safe_path(self.config_path)
        )
        return self.snapshot

    @staticmethod
    def _validate_config(path: Path) -> None:
        if "\x00" in str(path) or not path.is_absolute():
            raise ValueError("cloudflared config path must be an absolute filesystem path")
        if path.suffix.lower() not in {".yml", ".yaml"}:
            raise ValueError("cloudflared config must be a YAML file")
        if not path.is_file():
            raise ValueError("cloudflared config file does not exist")
        if path.stat().st_size > 256 * 1024:
            raise ValueError("cloudflared config exceeds the 256 KiB bound")
        text = path.read_text(encoding="utf-8", errors="strict")
        if "token:" in text.lower() or "--token" in text.lower():
            raise ValueError("raw tunnel tokens are not accepted in exportable config")

    @staticmethod
    def _safe_path(path: Path) -> str:
        return f"…/{path.name}"

    def start(self, *, remote_enabled: bool) -> TunnelSnapshot:
        if not remote_enabled:
            stopped = self.stop()
            if stopped.status is TunnelStatus.ERROR:
                return stopped
            self.snapshot = TunnelSnapshot(TunnelStatus.OFF)
            return self.snapshot
        detected = self.detect()
        if detected.status not in {TunnelStatus.STOPPED, TunnelStatus.ONLINE}:
            return detected
        if self.process is not None and self.process.poll() is None:
            self.snapshot = TunnelSnapshot(TunnelStatus.ONLINE, detected.executable, detected.config)
            return self.snapshot
        assert detected.executable is not None and self.config_path is not None
        try:
            self.process = subprocess.Popen(
                [detected.executable, "tunnel", "--config", str(self.config_path), "run"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
        except OSError:
            self.snapshot = TunnelSnapshot(
                TunnelStatus.ERROR, detected.executable, detected.config, "cloudflared could not be started"
            )
            return self.snapshot
        self.snapshot = TunnelSnapshot(TunnelStatus.STARTING, detected.executable, detected.config)
        return self.snapshot

    def poll(self) -> TunnelSnapshot:
        if self.process is None:
            return self.snapshot
        code = self.process.poll()
        if code is None:
            self.snapshot = TunnelSnapshot(TunnelStatus.ONLINE, self.snapshot.executable, self.snapshot.config)
        else:
            self.snapshot = TunnelSnapshot(
                TunnelStatus.ERROR if code else TunnelStatus.STOPPED,
                self.snapshot.executable,
                self.snapshot.config,
                None if code == 0 else "cloudflared exited unexpectedly",
            )
        return self.snapshot

    def stop(self, *, timeout: float = 5.0) -> TunnelSnapshot:
        process = self.process
        stop_error: str | None = None
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                stop_error = "cloudflared terminate request failed"
            try:
                process.wait(timeout=max(0.1, timeout))
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except OSError:
                    self.snapshot = TunnelSnapshot(
                        TunnelStatus.ERROR,
                        self.snapshot.executable,
                        self.snapshot.config,
                        stop_error or "cloudflared kill request failed",
                    )
                    return self.snapshot
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    self.snapshot = TunnelSnapshot(
                        TunnelStatus.ERROR,
                        self.snapshot.executable,
                        self.snapshot.config,
                        "cloudflared shutdown timed out",
                    )
                    return self.snapshot
            except OSError:
                stop_error = stop_error or "cloudflared shutdown status could not be read"
        self.process = None
        self.snapshot = TunnelSnapshot(
            TunnelStatus.ERROR if stop_error else TunnelStatus.STOPPED,
            self.snapshot.executable,
            self.snapshot.config,
            stop_error,
        )
        return self.snapshot
