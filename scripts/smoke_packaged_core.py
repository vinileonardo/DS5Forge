#!/usr/bin/env python3
"""Exercise HTTP and WebSocket transport through the packaged core executable.

This intentionally talks to a real Uvicorn server over loopback. ASGI-only tests
cannot detect a missing Uvicorn WebSocket protocol implementation inside the
PyInstaller bundle.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ORIGIN = "http://tauri.localhost"
WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class SmokeFailure(RuntimeError):
    """Raised when the packaged transport contract is not usable."""


def _read_exact(sock: socket.socket, buffered: bytearray, size: int) -> bytes:
    while len(buffered) < size:
        chunk = sock.recv(max(4096, size - len(buffered)))
        if not chunk:
            raise SmokeFailure("WebSocket closed before the first frame completed")
        buffered.extend(chunk)
    result = bytes(buffered[:size])
    del buffered[:size]
    return result


def read_server_text_frame(sock: socket.socket, buffered: bytes = b"") -> str:
    """Read one unmasked, non-fragmented server text frame."""

    data = bytearray(buffered)
    first, second = _read_exact(sock, data, 2)
    if not first & 0x80:
        raise SmokeFailure("Expected the initial WebSocket snapshot in a single FIN frame")
    if first & 0x0F != 0x1:
        raise SmokeFailure(f"Expected a text WebSocket frame, got opcode {first & 0x0F}")
    if second & 0x80:
        raise SmokeFailure("Server WebSocket frames must not be masked")

    length = second & 0x7F
    if length == 126:
        length = int.from_bytes(_read_exact(sock, data, 2), "big")
    elif length == 127:
        length = int.from_bytes(_read_exact(sock, data, 8), "big")
    payload = _read_exact(sock, data, length)
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SmokeFailure("Initial WebSocket frame is not valid UTF-8") from exc


def websocket_snapshot(host: str, port: int, *, timeout: float = 5.0) -> dict[str, Any]:
    """Perform a browser-like RFC6455 handshake and return the first JSON frame."""

    key = base64.b64encode(os.urandom(16)).decode("ascii")
    expected_accept = base64.b64encode(hashlib.sha1(f"{key}{WEBSOCKET_GUID}".encode()).digest()).decode("ascii")
    request = (
        "GET /api/v1/ws HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Origin: {ORIGIN}\r\n"
        "Connection: Upgrade\r\n"
        "Upgrade: websocket\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "\r\n"
    ).encode("ascii")

    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(request)
        response = bytearray()
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(4096)
            if not chunk:
                raise SmokeFailure("Server closed during WebSocket handshake")
            response.extend(chunk)
            if len(response) > 64 * 1024:
                raise SmokeFailure("WebSocket handshake headers exceeded the safety bound")

        raw_headers, remainder = bytes(response).split(b"\r\n\r\n", 1)
        lines = raw_headers.decode("iso-8859-1").split("\r\n")
        if not lines or " 101 " not in f" {lines[0]} ":
            raise SmokeFailure(f"Expected WebSocket HTTP 101, got {lines[0] if lines else 'no status line'}")

        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
        if headers.get("sec-websocket-accept") != expected_accept:
            raise SmokeFailure("WebSocket Sec-WebSocket-Accept did not match the client key")

        text = read_server_text_frame(sock, remainder)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SmokeFailure("Initial WebSocket frame is not valid JSON") from exc
    if not isinstance(payload, dict) or payload.get("type") != "state.snapshot" or payload.get("version") != 1:
        raise SmokeFailure("WebSocket did not start with a version-1 state.snapshot event")
    return payload


def _request_json(url: str, *, method: str = "GET", timeout: float = 5.0) -> dict[str, Any]:
    request = urllib.request.Request(url, method=method, headers={"Origin": ORIGIN, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise SmokeFailure(f"Expected HTTP 200 from {url}, got {response.status}")
        allow_origin = response.headers.get("Access-Control-Allow-Origin")
        if allow_origin != ORIGIN:
            raise SmokeFailure(f"Expected CORS origin {ORIGIN}, got {allow_origin!r}")
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise SmokeFailure(f"Expected a JSON object from {url}")
    return payload


def wait_for_health(process: subprocess.Popen[bytes], host: str, port: int, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    url = f"http://{host}:{port}/api/v1/health"
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SmokeFailure(f"Packaged core exited before health was reachable (exit={process.returncode})")
        try:
            payload = _request_json(url, timeout=1.0)
            if payload.get("process_alive") is not True:
                raise SmokeFailure("Packaged core health did not report process_alive=true")
            return payload
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError, SmokeFailure) as exc:
            last_error = exc
            time.sleep(0.2)
    raise SmokeFailure(f"Packaged core health was not reachable within {timeout:.1f}s: {last_error}")


def _windows_image_pids(image_name: str) -> set[int]:
    if os.name != "nt":
        return set()
    result = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    pids: set[int] = set()
    for row in csv.reader(result.stdout.splitlines()):
        if len(row) < 2 or row[0].casefold() != image_name.casefold():
            continue
        try:
            pids.add(int(row[1]))
        except ValueError:
            continue
    return pids


def _wait_for_windows_pids_gone(image_name: str, pids: set[int], timeout: float = 5.0) -> set[int]:
    if os.name != "nt" or not pids:
        return set()
    deadline = time.monotonic() + timeout
    remaining = pids
    while remaining and time.monotonic() < deadline:
        remaining = pids.intersection(_windows_image_pids(image_name))
        if remaining:
            time.sleep(0.2)
    return remaining


def _stop_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()


def smoke(executable: Path, *, host: str, port: int, startup_timeout: float) -> None:
    if not executable.is_file():
        raise SmokeFailure(f"Packaged core executable not found: {executable}")

    command = [str(executable), "--headless", "--host", host, "--port", str(port)]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    baseline_pids = _windows_image_pids(executable.name)
    launched_pids: set[int] = set()
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(
            command,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
        try:
            health = wait_for_health(process, host, port, startup_timeout)
            if os.name == "nt":
                for _ in range(10):
                    launched_pids.update(_windows_image_pids(executable.name) - baseline_pids)
                    if process.pid in launched_pids and len(launched_pids) >= 2:
                        break
                    time.sleep(0.1)
                launched_pids.add(process.pid)
            snapshot = websocket_snapshot(host, port)
            state = snapshot.get("payload", {}).get("state", {}) if isinstance(snapshot.get("payload"), dict) else {}
            print(
                "packaged core transport OK: "
                f"health={health.get('status', 'unknown')} "
                f"connection={state.get('connection', 'unknown')} websocket=101+state.snapshot"
            )
            try:
                _request_json(f"http://{host}:{port}/api/v1/lifecycle/stop", method="POST", timeout=5.0)
            except (OSError, urllib.error.URLError, SmokeFailure):
                # The shutdown callback may tear the one-file child down before
                # the HTTP response flushes. Process exit is the authoritative result.
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired as exc:
                raise SmokeFailure("Packaged core did not exit after lifecycle stop") from exc
            remaining = _wait_for_windows_pids_gone(executable.name, launched_pids)
            if remaining:
                raise SmokeFailure(
                    "Packaged core left Windows process(es) alive after lifecycle stop: "
                    + ", ".join(str(pid) for pid in sorted(remaining))
                )
        except Exception:
            output.seek(0)
            captured = output.read().decode("utf-8", errors="replace")[-8000:]
            if captured:
                print("--- packaged core output ---", file=sys.stderr)
                print(captured, file=sys.stderr)
            raise
        finally:
            _stop_process_tree(process)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--startup-timeout", type=float, default=30.0)
    args = parser.parse_args()
    try:
        smoke(args.executable.resolve(), host=args.host, port=args.port, startup_timeout=args.startup_timeout)
    except (SmokeFailure, OSError, subprocess.SubprocessError) as exc:
        print(f"packaged core smoke failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
