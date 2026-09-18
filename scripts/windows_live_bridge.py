#!/usr/bin/env python3
"""Live diagnostics bridge from the WSL checkout to the installed Windows app.

This tool is development-only. It never starts a listener, changes firewall
rules, installs drivers or exposes DS5Forge remotely. It talks to the loopback
API already owned by the Windows core and uses PowerShell only for read-only
Windows process/device inspection.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API_BASE = "http://127.0.0.1:8765/api/v1"
WS_URL = "ws://127.0.0.1:8765/api/v1/ws"
WS_ORIGIN = "http://127.0.0.1:5173"
ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
XINPUT_PROBE = ROOT / "scripts" / "windows_xinput_probe.py"


def http_json(path: str) -> Any:
    target = path if path.startswith("http://") or path.startswith("https://") else f"{API_BASE}/{path.lstrip('/')}"
    request = urllib.request.Request(target, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": exc.code, "url": target, "body": _decode_json(raw)}
    except Exception as exc:
        return {"ok": False, "url": target, "error": str(exc)}
    return {"ok": True, "status": 200, "url": target, "body": _decode_json(raw)}


def powershell_json(script: str, *, timeout: float = 10.0) -> Any:
    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        f"[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; $OutputEncoding=[System.Text.Encoding]::UTF8; $ErrorActionPreference='Stop'; & {{ {script} }} | ConvertTo-Json -Depth 8 -Compress",
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        return {"ok": False, "error": (completed.stderr or completed.stdout).strip()}
    output = completed.stdout.strip()
    return {"ok": True, "body": _decode_json(output) if output else None}


def process_snapshot() -> Any:
    result = powershell_json(
        "$processes=@(Get-CimInstance Win32_Process | Where-Object { "
        "$_.Name -in @('ds5forge.exe','ds5forge-core.exe') } | "
        "Select-Object Name,ProcessId,ParentProcessId,ExecutablePath,CommandLine,CreationDate); "
        "$listeners=@(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | "
        "Select-Object LocalAddress,LocalPort,OwningProcess); "
        "[pscustomobject]@{processes=$processes;listeners=$listeners}"
    )
    body = result.get("body") if isinstance(result, dict) else None
    if not result.get("ok") or not isinstance(body, dict):
        return result
    processes = body.get("processes") or []
    if isinstance(processes, dict):
        processes = [processes]
    listeners = body.get("listeners") or []
    if isinstance(listeners, dict):
        listeners = [listeners]
    shell_pids = {item.get("ProcessId") for item in processes if item.get("Name") == "ds5forge.exe"}
    sidecar_roots = [
        item.get("ProcessId")
        for item in processes
        if item.get("Name") == "ds5forge-core.exe" and item.get("ParentProcessId") in shell_pids
    ]
    api_owners = [item.get("OwningProcess") for item in listeners]
    body["sidecar_roots"] = sidecar_roots
    body["api_owners"] = api_owners
    body["note"] = (
        "PyInstaller one-file uses a parent bootloader plus a child application process; "
        "multiple ds5forge-core.exe rows can represent one normal sidecar process tree."
    )
    return result


def dualsense_snapshot() -> Any:
    return powershell_json(
        "@(Get-PnpDevice -PresentOnly | Where-Object { "
        "$_.InstanceId -match 'VID_054C&PID_0CE6' -or $_.FriendlyName -match 'DualSense' } | "
        "Select-Object Class,FriendlyName,InstanceId,Status)"
    )


def input_stack_snapshot() -> Any:
    """Inspect common input wrappers plus present game-controller PnP devices."""

    return powershell_json(
        "$names=@('steam.exe','DSX.exe','ds4windows.exe','rewasd.exe','joytokey.exe','antimicrox.exe','KingdomCome.exe'); "
        "$processes=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in $names } | "
        "Select-Object Name,ProcessId,ParentProcessId,ExecutablePath,CommandLine); "
        "$devices=@(Get-PnpDevice -PresentOnly -Class HIDClass | Where-Object { "
        "$_.InstanceId -match 'VID_054C&PID_0CE6' -or $_.FriendlyName -match 'Xbox|XINPUT|DualSense|Wireless Controller' "
        "} | ForEach-Object { "
        "$device=$_; $parent=$null; $location=$null; $service=$null; "
        "try { $parent=(Get-PnpDeviceProperty -InstanceId $device.InstanceId -KeyName 'DEVPKEY_Device_Parent' -ErrorAction Stop).Data } catch {}; "
        "try { $location=(Get-PnpDeviceProperty -InstanceId $device.InstanceId -KeyName 'DEVPKEY_Device_LocationInfo' -ErrorAction Stop).Data } catch {}; "
        "try { $service=(Get-PnpDeviceProperty -InstanceId $device.InstanceId -KeyName 'DEVPKEY_Device_Service' -ErrorAction Stop).Data } catch {}; "
        "[pscustomobject]@{Class=$device.Class;FriendlyName=$device.FriendlyName;InstanceId=$device.InstanceId;Status=$device.Status;Parent=$parent;Location=$location;Service=$service} "
        "}); [pscustomobject]@{processes=$processes;devices=$devices}",
        timeout=20.0,
    )


def xinput_snapshot() -> Any:
    """Probe the four Windows XInput slots without creating any device."""

    try:
        windows_path = subprocess.run(
            ["wslpath", "-w", str(XINPUT_PROBE)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=True,
        ).stdout.strip()
        completed = subprocess.run(
            ["py.exe", "-3.12", windows_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    raw = completed.stdout.strip()
    if completed.returncode != 0:
        return {"ok": False, "error": (completed.stderr or raw or "XInput probe failed").strip()}
    return _decode_json(raw) if raw else {"ok": False, "error": "XInput probe returned no output"}


def hidhide_snapshot() -> Any:
    cli = r"C:\Program Files\Nefarius Software Solutions\HidHide\x64\HidHideCLI.exe"
    script = (
        f"$cli='{cli}'; "
        "if (-not (Test-Path -LiteralPath $cli)) { "
        "[pscustomobject]@{installed=$false} "
        "} else { "
        "$cloak=& $cli --cloak-state; $apps=& $cli --app-list; $hidden=& $cli --dev-list; $gaming=& $cli --dev-gaming; "
        '[pscustomobject]@{installed=$true; cloak=$cloak; applications=@($apps); hidden_devices=@($hidden); gaming_json=($gaming -join "`n")} '
        "}"
    )
    result = powershell_json(script)
    if result.get("ok") and isinstance(result.get("body"), dict):
        body = result["body"]
        gaming = body.get("gaming_json")
        if isinstance(gaming, str):
            body["gaming_devices"] = _decode_json(gaming)
            body.pop("gaming_json", None)
    return result


def snapshot() -> dict[str, Any]:
    endpoints = {
        "health": "health",
        "info": "info",
        "state": "state",
        "foreground": "foreground",
        "automation": "automation",
        "game_candidates": "games/candidates",
        "duplicate_input": "diagnostics/duplicate-input",
        "input_isolation_capability": "input-isolation/capabilities",
        "input_isolation_status": "input-isolation/status",
        "exclusive_capability": "exclusive/capabilities",
        "exclusive_status": "exclusive/status",
    }
    return {
        "api": {name: http_json(path) for name, path in endpoints.items()},
        "windows": {
            "processes": process_snapshot(),
            "dualsense": dualsense_snapshot(),
            "input_stack": input_stack_snapshot(),
            "xinput": xinput_snapshot(),
            "hidhide": hidhide_snapshot(),
        },
    }


def websocket_events(count: int, timeout_seconds: float) -> int:
    ws_module = FRONTEND / "node_modules" / "ws"
    if not ws_module.exists():
        print(json.dumps({"ok": False, "error": "frontend/node_modules/ws is unavailable; run npm ci first"}))
        return 2
    program = r"""
const WebSocket = require(process.argv[1]);
const url = process.argv[2];
const origin = process.argv[3];
const wanted = Number(process.argv[4]);
const timeoutMs = Number(process.argv[5]);
let seen = 0;
const ws = new WebSocket(url, { origin });
const timer = setTimeout(() => {
  console.error(JSON.stringify({ok:false,error:"timeout",seen}));
  ws.terminate();
  process.exit(seen > 0 ? 0 : 2);
}, timeoutMs);
ws.on("open", () => console.error(JSON.stringify({ok:true,event:"open"})));
ws.on("message", data => {
  process.stdout.write(data.toString() + "\n");
  seen += 1;
  if (seen >= wanted) {
    clearTimeout(timer);
    ws.close();
    setTimeout(() => process.exit(0), 25);
  }
});
ws.on("error", error => {
  clearTimeout(timer);
  console.error(JSON.stringify({ok:false,error:String(error)}));
  process.exit(2);
});
"""
    completed = subprocess.run(
        [
            "node",
            "-e",
            program,
            str(ws_module),
            WS_URL,
            WS_ORIGIN,
            str(max(1, count)),
            str(max(250, int(timeout_seconds * 1000))),
        ],
        cwd=FRONTEND,
        timeout=max(2.0, timeout_seconds + 2.0),
        check=False,
    )
    return completed.returncode


def _decode_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect the live Windows DS5Forge instance from WSL.")
    sub = parser.add_subparsers(dest="command", required=False)
    sub.add_parser("snapshot", help="API + Windows process/device/HidHide snapshot (default)")
    api_parser = sub.add_parser("api", help="GET one local API path")
    api_parser.add_argument("path", help="Path under /api/v1, e.g. state or controller/lightbar")
    sub.add_parser("processes", help="Read installed ds5forge/ds5forge-core Windows processes")
    sub.add_parser("dualsense", help="Read present DualSense Windows PnP devices")
    sub.add_parser("input-stack", help="Read common input wrappers and present controller PnP devices")
    sub.add_parser("xinput", help="Read the four Windows XInput slots without creating a device")
    sub.add_parser("hidhide", help="Read HidHide cloak, allowlist and hidden-device state")
    ws_parser = sub.add_parser("ws", help="Read live local WebSocket events")
    ws_parser.add_argument("--count", type=int, default=5)
    ws_parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    command = args.command or "snapshot"
    if command == "snapshot":
        print_json(snapshot())
        return 0
    if command == "api":
        print_json(http_json(args.path))
        return 0
    if command == "processes":
        print_json(process_snapshot())
        return 0
    if command == "dualsense":
        print_json(dualsense_snapshot())
        return 0
    if command == "input-stack":
        print_json(input_stack_snapshot())
        return 0
    if command == "xinput":
        print_json(xinput_snapshot())
        return 0
    if command == "hidhide":
        print_json(hidhide_snapshot())
        return 0
    if command == "ws":
        return websocket_events(args.count, args.timeout)
    parser.error(f"unsupported command: {command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
