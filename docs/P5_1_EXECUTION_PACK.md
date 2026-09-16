# P5.1 Execution Pack — Windows Live Validation and Runtime Correctness

Status: implementation pending on `fix/p5.1-windows-live-validation`.

## Goal

Close the gaps exposed by real Windows/DualSense validation of `v0.4.0-rc.7`. P5.1 is not complete until the installed Windows build is exercised against a physical wired DualSense and the live application can be inspected/controlled from the development environment without relying on screenshots alone.

## 1. Game lifecycle: process presence is authoritative

### Problem

P5 currently derives the active game from the foreground window. Alt-Tab therefore deactivates a game even while its configured executable is still alive.

### Required behavior

- Track registered game processes independently of the foreground window.
- A configured game becomes active when a matching executable is observed running.
- The active game remains active while at least one matching configured process is alive, even when another application owns the foreground window.
- Exit policy runs only after the active game's matching process set reaches zero, not on Alt-Tab/desktop transitions.
- Foreground remains a separate observation used for UX, conflict resolution and deterministic selection when multiple registered games run.
- If multiple registered games run simultaneously: foreground matching game wins; otherwise retain the current active game while it remains alive; if it exits, select the most recently observed eligible game deterministically.
- Manual override semantics remain bounded to the active game/process context.
- Adaptive-trigger ownership/profile application follows process-lifetime activation; foreground status remains separately observable.

### Candidates

- `running` must mean OS process presence, not only the current foreground process.
- Do not populate the game picker with arbitrary recent desktop applications as if they were games.
- Always surface registered games that are currently running.
- Candidate rows must expose process name, path and source without concatenated text.

## 2. Games UX and localization

### Problems observed in rc.7

- Long executable paths overflow cards.
- Registry action buttons can be pushed outside the card.
- Candidate title/path/source can render as one concatenated string.
- Backend-generated rule reasons and conflict diagnostic messages remain English while the UI is pt-BR.

### Required behavior

- All cards and rows use `min-width: 0` where required.
- Long paths use safe wrapping (`overflow-wrap:anywhere` or equivalent) without widening the grid.
- Row actions remain inside their card at desktop and mobile widths.
- Candidate name/path/source are visually distinct fields.
- Rule and conflict responses expose stable machine-readable codes/parameters; the frontend localizes presentation strings. Raw English backend prose must not leak into pt-BR primary UI.
- Add regression coverage for 260+ character paths and narrow desktop/mobile widths.

## 3. Exclusive / double-input must become operational

### Current rc.7 gap

The UI exposes `HIDMaestro+HidHide`, but the packaged runtime composes the verifier without a configured helper path, pinned hash, verified signature/provenance or Windows validation. Therefore output reports and physical suppression remain false and Exclusive cannot be enabled.

### Required behavior

- Ship or deterministically provision the approved Exclusive helper/provider path as part of the Windows product flow.
- Pin and verify the exact helper artifact/hash expected by the release.
- Verify provider provenance before enabling Exclusive.
- Detect/install prerequisites explicitly with user consent; no silent network install.
- Validate HidHide suppression against the physical wired DualSense.
- Validate virtual output reports using the selected HIDMaestro profile.
- Exclusive enable is transactional: virtual output ready -> physical suppression verified -> mirroring live -> session exposed as enabled.
- Any failure rolls back suppression and virtual output.
- Recovery must cover helper crash, Core crash/restart, app Quit, update and uninstall.
- `double_input_risk=false` only when physical suppression is actually verified for the live session.

### Acceptance evidence

- `joy.cpl`/equivalent shows only the intended game-facing device while Exclusive is active.
- A real game receives a single logical controller.
- Disconnect/reconnect, Alt-Tab, game exit and app exit do not leave the physical controller hidden or synthetic state stuck.

## 4. Live Dev Bridge: WSL/Windows/app real-time loop

### Goal

Allow development and validation against the currently running Windows application from an authorized terminal/MCP session.

### Production-safe design

- Keep the existing loopback API as the source of truth.
- Add a developer CLI under `scripts/dev/` that can target the live local Core API.
- Provide `status`, `state`, `events --follow`, `foreground`, `games`, `exclusive`, `lightbar`, `triggers`, `player-leds`, `haptics` and `logs --follow` commands.
- Provide a debug-only simulation surface gated by an explicit environment variable/build flag; production builds must not expose injection endpoints.
- Debug simulation supports deterministic foreground/process inventory, controller telemetry, audio envelope and lifecycle fixtures for automated UI/runtime tests.
- Use a separate dev API port/data directory/app identity where needed so the installed release and dev shell cannot corrupt each other's state.
- Windows-native build/test commands must execute from a Windows-local path to avoid WSL UNC/Cargo locking issues.
- Add a one-command Windows/WSL launcher that starts the Core/dev shell, tails logs and verifies API/WebSocket connectivity.

### Suggested CLI examples

```text
python scripts/dev/ds5forge_live.py status
python scripts/dev/ds5forge_live.py state --watch
python scripts/dev/ds5forge_live.py events --follow
python scripts/dev/ds5forge_live.py games running
python scripts/dev/ds5forge_live.py exclusive status
python scripts/dev/ds5forge_live.py lightbar pulse --intensity 50
python scripts/dev/ds5forge_live.py triggers reactive --fixture explosion
```

## Gates

P5.1 source gates inherit all P5 gates and add:

- process-lifetime game automation unit/integration tests;
- multiple-running-game selection tests;
- Alt-Tab does not deactivate a running game;
- exit policy executes only on process exit;
- candidate filtering/process inventory tests;
- pt-BR parity for backend-derived rule/conflict states;
- long-path responsive visual tests;
- live CLI/API smoke tests;
- Windows Rust/Tauri checks from Windows-local storage;
- real packaged app + physical DualSense validation for Exclusive, lightbar, adaptive triggers, touchpad and haptics.

## Release rule

Do not publish the next RC as hardware-complete while Exclusive is unavailable or while game activation still depends only on foreground ownership. Keep Windows/hardware evidence explicit and reproducible.
