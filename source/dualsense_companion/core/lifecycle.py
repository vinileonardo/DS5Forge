"""Bounded desktop/core lifecycle supervision primitives.

The Tauri shell is the production owner of the Python sidecar, but keeping the
state machine and probe semantics platform-neutral makes startup, crash-loop
and teardown behavior testable without Windows or a controller.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class LifecycleState(StrEnum):
    DESKTOP_STARTING = "desktop_starting"
    CORE_STARTING = "core_starting"
    CORE_READY = "core_ready"
    APPLICATION_READY = "application_ready"
    CORE_START_FAILED = "core_start_failed"
    CORE_TIMEOUT = "core_timeout"
    CORE_CRASHED = "core_crashed"
    CORE_STOPPING = "core_stopping"
    CORE_STOPPED = "core_stopped"
    SHUTDOWN_TIMEOUT = "shutdown_timeout"


@dataclass(frozen=True, slots=True)
class LifecycleSnapshot:
    state: LifecycleState
    attempt: int = 0
    pid: int | None = None
    message: str | None = None
    changed_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "attempt": self.attempt,
            "pid": self.pid,
            "message": self.message,
            "changed_at": self.changed_at,
        }


class ProcessHandle(Protocol):
    @property
    def pid(self) -> int | None: ...

    def is_alive(self) -> bool: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float) -> bool: ...


class HealthProbe(Protocol):
    def __call__(self) -> dict[str, Any]: ...


class PopenHandle:
    """Small adapter around ``subprocess.Popen`` with deterministic semantics."""

    def __init__(self, process: subprocess.Popen[Any]) -> None:
        self.process = process

    @property
    def pid(self) -> int | None:
        return self.process.pid

    def is_alive(self) -> bool:
        return self.process.poll() is None

    def terminate(self) -> None:
        self.process.terminate()

    def kill(self) -> None:
        self.process.kill()

    def wait(self, timeout: float) -> bool:
        try:
            self.process.wait(timeout=max(0.0, timeout))
        except subprocess.TimeoutExpired:
            return False
        return True


@dataclass(frozen=True, slots=True)
class SupervisorConfig:
    startup_timeout: float = 20.0
    shutdown_timeout: float = 8.0
    poll_interval: float = 0.25
    max_restarts: int = 3
    backoff_initial: float = 0.5
    backoff_max: float = 8.0

    def __post_init__(self) -> None:
        if self.startup_timeout <= 0 or self.shutdown_timeout <= 0:
            raise ValueError("lifecycle timeouts must be positive")
        if self.poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        if self.max_restarts < 0:
            raise ValueError("max_restarts must not be negative")


class CoreSupervisor:
    """Supervise one child process with bounded readiness and recovery."""

    def __init__(
        self,
        process_factory: Callable[[], ProcessHandle],
        health_probe: HealthProbe,
        *,
        config: SupervisorConfig | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        on_state: Callable[[LifecycleSnapshot], None] | None = None,
    ) -> None:
        self.process_factory = process_factory
        self.health_probe = health_probe
        self.config = config or SupervisorConfig()
        self.clock = clock
        self.sleeper = sleeper
        self.on_state = on_state
        self.process: ProcessHandle | None = None
        self.snapshot = LifecycleSnapshot(LifecycleState.DESKTOP_STARTING)
        self.restart_count = 0

    def _set(self, state: LifecycleState, *, message: str | None = None, attempt: int | None = None) -> None:
        self.snapshot = LifecycleSnapshot(
            state,
            attempt=self.snapshot.attempt if attempt is None else attempt,
            pid=self.process.pid if self.process is not None else None,
            message=message,
        )
        if self.on_state is not None:
            self.on_state(self.snapshot)

    @staticmethod
    def _ready(payload: dict[str, Any]) -> bool:
        status = str(payload.get("status", "")).lower()
        if status in {"healthy", "ready", "ok"}:
            return True
        health = payload.get("health")
        return (
            isinstance(health, dict)
            and bool(health.get("process_alive"))
            and status
            not in {
                "failed",
                "error",
                "offline",
            }
        )

    def start(self) -> LifecycleSnapshot:
        if self.snapshot.state in {LifecycleState.CORE_READY, LifecycleState.APPLICATION_READY}:
            return self.snapshot
        self._set(LifecycleState.DESKTOP_STARTING, attempt=self.restart_count)
        self._set(LifecycleState.CORE_STARTING, attempt=self.restart_count)
        try:
            self.process = self.process_factory()
        except Exception:
            self._set(LifecycleState.CORE_START_FAILED, message="core process could not start")
            return self.snapshot
        deadline = self.clock() + self.config.startup_timeout
        last_error = "core health endpoint did not report ready"
        while self.clock() < deadline:
            if not self.process.is_alive():
                self._set(LifecycleState.CORE_CRASHED, message="core exited before readiness")
                return self.snapshot
            try:
                payload = self.health_probe()
                if self._ready(payload):
                    self._set(LifecycleState.CORE_READY)
                    self._set(LifecycleState.APPLICATION_READY)
                    return self.snapshot
                last_error = str(payload.get("message") or payload.get("status") or last_error)
            except Exception:
                # A bounded probe failure is expected during boot.  It must not
                # be logged with response bodies, which could contain secrets.
                last_error = "core health probe failed"
            self.sleeper(min(self.config.poll_interval, max(0.0, deadline - self.clock())))
        self._set(LifecycleState.CORE_TIMEOUT, message=last_error)
        shutdown = self.stop()
        if shutdown.state is LifecycleState.SHUTDOWN_TIMEOUT:
            return shutdown
        self._set(LifecycleState.CORE_TIMEOUT, message=last_error)
        return self.snapshot

    def restart(self) -> LifecycleSnapshot:
        if self.restart_count >= self.config.max_restarts:
            self._set(LifecycleState.CORE_START_FAILED, message="restart limit reached")
            return self.snapshot
        self.restart_count += 1
        stopped = self.stop()
        if stopped.state is LifecycleState.SHUTDOWN_TIMEOUT:
            # Never replace a child that did not exit: doing so would orphan
            # the old process and make the bounded supervisor unsafe.
            return stopped
        self.sleeper(min(self.config.backoff_max, self.config.backoff_initial * (2 ** (self.restart_count - 1))))
        return self.start()

    def note_crash_and_recover(self) -> LifecycleSnapshot:
        self._set(LifecycleState.CORE_CRASHED, message="core process exited unexpectedly")
        return self.restart()

    def stop(self) -> LifecycleSnapshot:
        process = self.process
        if process is None:
            self._set(LifecycleState.CORE_STOPPED)
            return self.snapshot
        self._set(LifecycleState.CORE_STOPPING)
        termination_error: str | None = None
        try:
            process.terminate()
        except Exception:
            termination_error = "core terminate request failed"
        if not process.wait(self.config.shutdown_timeout):
            try:
                process.kill()
            except Exception:
                self._set(
                    LifecycleState.SHUTDOWN_TIMEOUT,
                    message=termination_error or "core kill request failed",
                )
                return self.snapshot
            if not process.wait(self.config.shutdown_timeout):
                self._set(LifecycleState.SHUTDOWN_TIMEOUT, message="core did not exit before shutdown timeout")
                return self.snapshot
        self.process = None
        self._set(LifecycleState.CORE_STOPPED, message=termination_error)
        return self.snapshot


def sidecar_command(executable: str, *, host: str = "127.0.0.1", port: int = 8765) -> list[str]:
    """Return the fixed, non-shell command used by packaging and tests."""

    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("the core sidecar may only bind to loopback")
    if not 1 <= int(port) <= 65535:
        raise ValueError("port must be between 1 and 65535")
    return [executable, "--headless", "--host", host, "--port", str(port)]
