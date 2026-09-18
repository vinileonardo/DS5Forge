"""Windows-only Exclusive provider boundary.

This module contains no Python HID implementation and deliberately does not
use ``pythonnet`` or an arbitrary shell.  A future signed helper owns the
HIDMaestro and HidHide calls.  Until its fixed path, hash, signature,
provenance and Windows validation are all supplied, capability remains false.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from ...domain.exclusive import ProviderProvenance

HELPER_PROTOCOL_VERSION = 1
HELPER_BASENAME = "DS5ForgeExclusiveHelper.exe"
PROVIDER_NAME = "HIDMaestro+HidHide"
REQUEST_TIMEOUT_SECONDS = 5.0
CLOSE_TIMEOUT_SECONDS = 1.0


class FixedSidecarVerifier:
    """Verify a user-provided helper without downloading or installing it."""

    def __init__(
        self,
        helper_path: Path | None,
        *,
        expected_sha256: str | None = None,
        signature_verified: bool = False,
        provenance_verified: bool = False,
        windows_validated: bool = False,
    ) -> None:
        self.helper_path = Path(helper_path) if helper_path is not None else None
        self.expected_sha256 = expected_sha256.lower() if expected_sha256 else None
        self.signature_verified = signature_verified
        self.provenance_verified = provenance_verified
        self.windows_validated = windows_validated
        self._cached: ProviderProvenance | None = None

    def inspect(self) -> ProviderProvenance:
        # Provenance is static for the process lifetime, and hashing the helper
        # on every capability/status read would be both wasteful and a source
        # of latency in the heartbeat/watchdog path.
        if self._cached is None:
            self._cached = self._inspect()
        return self._cached

    def _inspect(self) -> ProviderProvenance:
        evidence: list[str] = []
        actual_hash: str | None = None
        integrity_verified = False
        if sys.platform != "win32":
            evidence.append("Windows runtime is required")
        if self.helper_path is None:
            evidence.append("helper path was not configured")
        elif self.helper_path.name != HELPER_BASENAME:
            evidence.append(f"helper must be named {HELPER_BASENAME}")
        elif not self.helper_path.is_file():
            evidence.append("fixed helper path does not exist")
        else:
            actual_hash = _sha256(self.helper_path)
            integrity_verified = self.expected_sha256 is not None and actual_hash == self.expected_sha256
            if not integrity_verified:
                evidence.append("helper SHA-256 does not match the pinned release value")
        if not self.signature_verified:
            evidence.append("Authenticode signature is not verified")
        if not self.provenance_verified:
            evidence.append("helper provenance is not verified")
        if not self.windows_validated:
            evidence.append("Windows provider validation is pending")
        return ProviderProvenance(
            provider=PROVIDER_NAME,
            version=str(HELPER_PROTOCOL_VERSION),
            executable=str(self.helper_path) if self.helper_path else None,
            sha256=actual_hash,
            signature_verified=self.signature_verified,
            provenance_verified=self.provenance_verified,
            integrity_verified=integrity_verified,
            windows_validated=self.windows_validated,
            evidence=tuple(evidence) if evidence else ("fixed helper verified",),
        )


class FixedExclusiveSidecarClient:
    """Restricted JSON-lines client for the packaged helper.

    The command vector is fixed at construction.  ``shell=False`` and the
    executable-name check prevent a config value from becoming a command
    interpreter.  This client is never started unless the verifier passes.
    """

    def __init__(self, verifier: FixedSidecarVerifier) -> None:
        self.verifier = verifier
        self.process: subprocess.Popen[str] | None = None
        self._recovery_attempted = False

    @property
    def provenance(self) -> ProviderProvenance:
        return self.verifier.inspect()

    def start(self, *, token: str, generation: int) -> None:
        provenance = self.provenance
        if not provenance.verified or self.verifier.helper_path is None:
            raise RuntimeError("fixed Exclusive helper is not verified")
        self.process = subprocess.Popen(  # noqa: S603 - fixed, verified executable; shell is explicitly disabled
            [
                str(self.verifier.helper_path),
                "--protocol-version",
                str(HELPER_PROTOCOL_VERSION),
                "--parent-pid",
                str(os.getpid()),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            # stderr is intentionally discarded: a helper that writes enough
            # diagnostics to a pipe could otherwise fill the OS buffer and
            # deadlock the JSON-lines request/response loop.
            stderr=subprocess.DEVNULL,
            text=True,
            shell=False,
        )
        try:
            self.request({"op": "acquire", "token": token, "generation": generation})
        except Exception:
            # The process may have acquired provider state before returning a
            # malformed/rejected response.  Close it here because the caller
            # cannot yet mark the virtual transaction step as started.
            self.close()
            raise

    def request(self, payload: dict[str, Any], *, timeout: float = REQUEST_TIMEOUT_SECONDS) -> dict[str, Any]:
        process = self.process
        if process is None or process.stdin is None or process.stdout is None:
            raise RuntimeError("Exclusive helper is not running")
        if process.poll() is not None:
            raise RuntimeError("Exclusive helper exited before the request was sent")
        try:
            process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
            process.stdin.flush()
        except (OSError, BrokenPipeError, ValueError) as exc:
            raise RuntimeError("Exclusive helper stdin is not writable") from exc
        line = _read_protocol_line(process, timeout=timeout)
        if not line:
            raise RuntimeError("Exclusive helper closed its protocol")
        try:
            result = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Exclusive helper returned malformed JSON") from exc
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise RuntimeError(str(result.get("error", "Exclusive helper rejected the request")))
        return result

    def close(self) -> None:
        process, self.process = self.process, None
        if process is None:
            return
        try:
            # The release request is best-effort; process termination is not.
            if process.stdin is not None and process.poll() is None:
                try:
                    process.stdin.write(json.dumps({"op": "release"}) + "\n")
                    process.stdin.flush()
                except (OSError, BrokenPipeError, ValueError):
                    pass
        finally:
            _terminate_process(process)

    def recover_stale(self) -> None:
        """Ask a verified helper to clear orphaned provider/session state."""

        if self._recovery_attempted:
            return
        self._recovery_attempted = True
        provenance = self.provenance
        if not provenance.verified or self.verifier.helper_path is None:
            return
        process = subprocess.Popen(  # noqa: S603 - fixed, verified executable; shell is explicitly disabled
            [
                str(self.verifier.helper_path),
                "--protocol-version",
                str(HELPER_PROTOCOL_VERSION),
                "--parent-pid",
                str(os.getpid()),
                "--recover-stale",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            shell=False,
        )
        self.process = process
        try:
            self.request({"op": "recover_stale"})
        finally:
            self.close()


class WindowsHidMaestroProvider:
    """Structural provider for virtual DualSense reports through the helper."""

    def __init__(self, client: FixedExclusiveSidecarClient) -> None:
        self.client = client

    def capability(self) -> Any:
        provenance = self.client.provenance
        return _Capability(
            available=provenance.verified,
            installed=provenance.verified,
            output_reports=provenance.verified,
            provenance=provenance,
            reason=None if provenance.verified else "HIDMaestro helper verification is incomplete.",
        )

    def start(self, *, token: str, generation: int) -> None:
        self.client.start(token=token, generation=generation)

    def heartbeat(self, *, token: str, generation: int) -> None:
        self.client.request({"op": "heartbeat", "token": token, "generation": generation})

    def submit_state(
        self,
        input_state: Any,
        *,
        battery: Any,
        sequence: int,
        token: str,
        generation: int,
    ) -> tuple[bytes, ...]:
        result = self.client.request(
            {
                "op": "submit_state",
                "token": token,
                "generation": generation,
                "sequence": sequence,
                "input": input_state.to_dict(),
                "battery": battery.to_dict(),
            }
        )
        raw_reports = result.get("output_reports", [])
        if not isinstance(raw_reports, list) or len(raw_reports) > 32:
            raise RuntimeError("Exclusive helper returned an invalid output-report batch")
        reports: list[bytes] = []
        for encoded in raw_reports:
            if not isinstance(encoded, str):
                raise RuntimeError("Exclusive helper returned a non-string output report")
            try:
                report = bytes.fromhex(encoded)
            except ValueError as exc:
                raise RuntimeError("Exclusive helper returned malformed output-report hex") from exc
            if len(report) != 64 or report[0] != 0x02:
                raise RuntimeError("Exclusive helper returned a non-USB-DualSense output report")
            reports.append(report)
        return tuple(reports)

    def close(self, *, token: str, generation: int) -> None:
        try:
            self.client.request({"op": "release", "token": token, "generation": generation})
        finally:
            # Process termination must happen even when the release request
            # fails, times out or the helper already closed its protocol. The
            # caller still sees the release failure so it can report an
            # incomplete teardown honestly.
            self.client.close()

    def recover_stale(self) -> None:
        self.client.recover_stale()


class WindowsHidHideSuppressionProvider:
    """Session-blacklist boundary for HidHide, controlled only by the helper."""

    def __init__(self, client: FixedExclusiveSidecarClient) -> None:
        self.client = client

    def capability(self) -> Any:
        provenance = self.client.provenance
        return _SuppressionCapability(
            available=provenance.verified,
            verified=provenance.verified,
            session_scoped=provenance.verified,
            reason=None if provenance.verified else "HidHide session suppression validation is pending.",
        )

    def enable(self, *, token: str, generation: int) -> None:
        self.client.request({"op": "suppress", "token": token, "generation": generation})

    def heartbeat(self, *, token: str, generation: int) -> None:
        self.client.request({"op": "heartbeat", "token": token, "generation": generation})

    def disable(self, *, token: str, generation: int) -> None:
        self.client.request({"op": "unsuppress", "token": token, "generation": generation})

    def recover_stale(self) -> None:
        self.client.recover_stale()


class _Capability:
    def __init__(self, **values: Any) -> None:
        self.__dict__.update(values)


class _SuppressionCapability:
    def __init__(self, **values: Any) -> None:
        self.__dict__.update(values)


def _read_protocol_line(process: subprocess.Popen[str], *, timeout: float) -> str:
    """Read one JSON-lines response with a finite timeout.

    ``readline`` on a pipe has no portable timeout, especially on Windows, so
    a bounded worker thread performs the read.  On timeout the process is
    terminated to guarantee no helper is orphaned and to unblock the worker.
    """

    stream = process.stdout
    if stream is None:
        raise RuntimeError("Exclusive helper stdout is unavailable")
    result: dict[str, Any] = {}

    def reader() -> None:
        try:
            result["line"] = stream.readline()
        except Exception as exc:  # pragma: no cover - platform pipe failure
            result["error"] = exc

    worker = threading.Thread(target=reader, name="DS5ForgeExclusiveRead", daemon=True)
    worker.start()
    worker.join(max(0.1, float(timeout)))
    if worker.is_alive():
        _terminate_process(process)
        raise RuntimeError("Exclusive helper request timed out and was terminated")
    if "error" in result:
        raise RuntimeError(f"Exclusive helper read failed: {result['error']}")
    return str(result.get("line", ""))


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=CLOSE_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
        except OSError:  # pragma: no cover - already gone
            pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
