# P5.1 Windows Live Validation — 0.4.0-rc.8

Date: 2026-09-16
Branch: `fix/p5.1-windows-live-validation`
Base commit: `f882ce4b37e59c2d4cecc22f6dd2bb0e950d40b6`
Candidate: `0.4.0-rc.8`
Transport scope: wired USB only

## Result

**Technical GO for 0.4.0-rc.8.**

All automated gates, Windows packaged-core smoke, final NSIS installation checks, live process/game lifecycle validation, HidHide isolation validation, WebSocket/controller telemetry, lighting command-path validation and adaptive-trigger runtime validation passed.

Two physical effects remain explicitly classified as **PENDING HUMAN OBSERVATION**, not as failures: visible lightbar/pulse/intensity appearance and tactile adaptive-trigger feel. The software command path and controller output-report path for both are validated, but those sensory effects cannot be independently observed by an automated reviewer.

## P5.1 scope validated

- Process-running state owns game automation lifecycle; foreground is only a priority signal.
- Registered games remain active after Alt+Tab while their process remains alive.
- Running configured processes are exposed as game candidates even when they are not foreground.
- Games UX handles long executable/path/reason content without overflow and uses localized process-aware language.
- PT-BR covers candidate source, automation/profile origin, rule actions, dynamic rule reasons and compatibility conflict messages.
- Live Dev Bridge reads Windows process state, loopback API, DualSense PnP, HidHide state and WebSocket events from WSL.
- Remap physical-input isolation is operational through HidHide with transactional ownership and rollback.
- Lightbar/player-LED command path is reconciled through a single output transaction and software pulse/intensity logic.
- Adaptive-trigger preview and reactive runtime output reports are exercised against the wired DualSense.
- Packaged-core shutdown no longer hangs when WASAPI capture is blocked.

## Automated gates

### Python

- `ruff check source tests scripts`: PASS
- `ruff format --check source tests scripts`: PASS — 101 files formatted
- `mypy source`: PASS — 69 source files
- `python -m compileall -q source tests scripts`: PASS
- `pytest -q`: PASS — **183 passed**
- `scripts/validate_versions.py --expected 0.4.0-rc.8`: PASS
- `git diff --check`: PASS

### Frontend

- Prettier: PASS
- ESLint: PASS
- TypeScript: PASS
- Vitest: PASS — **15 files / 56 tests**
- Vite production build: PASS
- Playwright: PASS — **11/11**
- `npm audit --audit-level=high`: PASS — **0 vulnerabilities**

### Rust / Tauri / Windows MSVC

Final rerun used a Windows-local Cargo target directory with `CARGO_INCREMENTAL=0` because incremental compilation on the WSL UNC path cannot create its lock file.

- `cargo fmt --check`: PASS
- `cargo check --all-targets --all-features`: PASS
- `cargo clippy --all-targets --all-features -- -D warnings`: PASS
- package version observed by Cargo: `ds5forge v0.4.0-rc.8`

### PE subsystem

- final Tauri `ds5forge.exe`: PASS — Windows GUI subsystem
- final packaged `DS5ForgeCore.exe`: PASS — Windows GUI subsystem

## Packaged-core shutdown blocker and fix

An initial `0.4.0-rc.8` packaged smoke exposed a real shutdown blocker: `HapticsService.stop()` set the stop event, but the worker could remain blocked inside WASAPI `capture.read()`. Because the worker thread is non-daemon, the packaged sidecar did not exit after `/lifecycle/stop`.

The fix tracks the active capture and closes it from the caller thread during stop, unblocking the PortAudio/WASAPI read. Shutdown-induced read errors are ignored only after the stop event is set. A regression test blocks a fake capture in `read()` and proves that `close()` releases the worker and allows the service to join cleanly.

After rebuilding the PyInstaller core, the same packaged smoke passed:

- HTTP health reachable
- controller connected
- WebSocket upgrade + `state.snapshot` received
- lifecycle stop completed
- packaged core process tree disappeared

## Final Windows package / install

Final corrected core:

`C:\Users\Vini\AppData\Local\Temp\ds5forge-p51-rc8-dist3\DS5ForgeCore.exe`

Final NSIS:

`C:\Users\Vini\AppData\Local\Temp\ds5forge-p51-rc8-target\release\bundle\nsis\DS5Forge_0.4.0-rc.8_x64-setup.exe`

Installed successfully under:

`C:\Users\Vini\AppData\Local\DS5Forge`

Final post-install evidence:

- `GET /api/v1/app/info`: `0.4.0-rc.8`, Python `3.12.10`, Windows, `usb_wired_only`
- `GET /api/v1/health`: `healthy`
- controller: `connected`
- audio: `listening`
- touchpad: `ready`
- WebSocket: open + `state.snapshot` + live `controller.input`
- process tree: one Tauri shell and one normal PyInstaller sidecar tree (bootloader parent + application child)

## Process-driven game lifecycle evidence

A temporary hidden `PING.EXE` rule was used while Edge remained the actual foreground application.

Observed while `PING.EXE` was alive:

- candidate list reported `PING.EXE` as running
- automation kept `active_game_id="p51-live-probe"`
- reason: configured process was still running in the background

After terminating `PING.EXE`, automation returned to no active game. The temporary rule was removed.

This closes the P5 foreground-coupled lifecycle defect.

## HidHide input-isolation evidence

Provider detected:

- HidHide `1.5.230.0`
- CLI: `C:\Program Files\Nefarius Software Solutions\HidHide\x64\HidHideCLI.exe`
- current wired DualSense: `HID\VID_054C&PID_0CE6&MI_03\8&1121ad8a&0&0000`

Pre-state:

- cloak OFF
- DS5Forge not allowlisted
- one unrelated/pre-existing stale hidden-device entry existed

Remap isolation transaction:

1. registered the DS5Forge core in the HidHide application allowlist
2. hid the currently connected DualSense instance
3. enabled cloak
4. verified the transaction

Verified active state:

- isolation active: true
- owned by DS5Forge: true
- cloak enabled: true
- application registered: true
- current device hidden: true
- physical input visible: false
- duplicate-input risk: false
- suppression verified: true

While cloak was active, DS5Forge continued receiving `controller.input` over WebSocket at the expected bounded telemetry rate, proving the application allowlist retained controller access.

Rollback verification:

- cloak returned OFF
- DS5Forge application entry removed
- current device entry created by DS5Forge removed
- pre-existing stale hidden-device entry preserved
- compatibility returned to Native

Final post-install HidHide inspection confirms cloak OFF and no DS5Forge application residue.

## PyInstaller external-process fix

Before the final fix, packaged PyInstaller calls to `HidHideCLI --version` / `--dev-gaming` could stall for roughly ten seconds because the child inherited PyInstaller's adjusted Windows DLL search directory.

The HidHide provider now temporarily clears the Windows DLL directory only during child process creation and restores it immediately afterward. The final packaged build detects HidHide and the active DualSense promptly through the installed application.

## Lighting / Player LED evidence

The wired DualSense accepted the following live output sequence through the real Windows adapter:

1. red at 100% intensity
2. red at 20% intensity
3. lightbar disabled
4. blue slow pulse
5. reset

Player LED sequence also completed without adapter error:

- green lightbar
- player LEDs off
- player LEDs enabled at 0.5 intensity
- reset

Technical result: **PASS — command path, state transitions and output reports.**

Human sensory result: **PENDING HUMAN OBSERVATION — visible brightness/pulse/on-off behavior.**

## Adaptive-trigger evidence

Preview validation:

- left: resistance, force 90
- right: pulse
- preview duration: 2000 ms
- preview started, timed out normally and reset both triggers to `off`

Reactive-runtime validation used a temporary background `PING.EXE` game rule with `adaptive_trigger_mode="reactive"`. Real WASAPI loopback activity produced repeated `adaptive_trigger.changed` WebSocket events with:

- source: `reactive`
- `generated_effect=true`
- `output_supported=true`
- force changing at runtime, approximately 55 → 65 during the sample

The temporary process/rule was removed afterward.

Technical result: **PASS — adaptive trigger output-report path and runtime-reactive generation.**

Human sensory result: **PENDING HUMAN OBSERVATION — tactile trigger response.**

## Cleanup / release hygiene

- Compatibility final state: Native
- HidHide cloak final state: OFF
- DS5Forge HidHide allowlist residue: none
- temporary validation game/process: removed
- final controller telemetry: connected and live
- historical untracked review-scope artifacts are not part of P5.1 and must not be staged
- `frontend/src-tauri/binaries/` is a generated sidecar build input and must not be committed

## Decision

**GO (technical) for P5.1 / 0.4.0-rc.8.**

The candidate satisfies the automated, Windows integration, packaging, installation, live process lifecycle, duplicate-input isolation and controller command-path gates. Visual/tactile hardware behavior remains intentionally unclaimed until a human observer confirms it on the physical controller.
