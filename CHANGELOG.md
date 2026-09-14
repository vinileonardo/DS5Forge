# Changelog

All notable changes to DS5Forge will be documented in this file.

The project currently evolves from the upstream `Casliyan/DS5companion` baseline recorded in `UPSTREAM.md`.

## Unreleased — P1 PC-first UX / Web + Desktop — 2026-09-14

### Added

- React/TypeScript/Vite SPA shared by the browser and a thin Tauri 2 shell.
- Validated Zod contracts, local API client, structured errors and a single
  HTTP/WebSocket runtime projection with bounded reconnect behavior.
- Functional Overview, Haptics, Touchpad, Profiles, Diagnostics and Settings
  routes with explicit offline/stale/protocol-error states.
- Narrow HTTP/WebSocket origin policy for Vite dev/preview and
  `http://tauri.localhost`, with explicit HTTP browser-origin rejection (not
  CORS-only enforcement) plus API tests for loopback security.
- Frontend unit/component tests, deterministic Playwright core-flow fixtures,
  Vite build/lint/type gates and Windows Tauri CI validation.
- Realtime trust gate that waits for the mandatory initial `state.snapshot`
  before marking a WebSocket session online, plus keyboard-safe destructive
  confirmation and pending locks for live controller toggles.

### Preserved and deferred

- The Python core remains the only controller/WASAPI/Windows HID authority.
- The `customtkinter` GUI remains available as a fallback.
- P1 adds no Bluetooth/wireless, P2 controller lab, P3 compatibility, or P4
  installer/sidecar/tray/updater functionality.
- Physical Windows + wired DualSense evidence remains `HARDWARE VALIDATION PENDING`.

## 0.1.0 — P0 Foundation / Core Authority — 2026-09-14

### Added

- `CoreFacade` as the single application authority shared by the legacy GUI and local API.
- Explicit controller lifecycle with `disconnected`, `connecting`, `connected`, `reconnecting`, `stopping` and error handling.
- Frozen runtime snapshots, versioned state publication and bounded event subscriptions.
- Windows platform adapters for `pydualsense`, WASAPI loopback and `SendInput`.
- Pure/testable DSP layer for the existing audio-driven rumble algorithm.
- Semantic touchpad gesture interpreter separated from Windows mouse output.
- Versioned configuration repository with validation, atomic persistence and safe fallback.
- Bundled profile protection and separate user profile storage.
- Local-only REST API under `/api/v1`.
- Versioned WebSocket realtime channel with initial snapshot and bounded event delivery.
- Health and diagnostics contracts with structured error codes.
- Headless execution mode using the same core as the legacy GUI.
- Python package metadata, reproducible Python 3.12 development setup and wheel build.
- GitHub Actions checks for Linux static/tests and Windows import/PyInstaller packaging.
- Architecture, API, development, migration and validation documentation.
- Automated regression tests for lifecycle, config, profiles, API, WebSocket, DSP, haptics, touchpad, WASAPI and Windows mouse output boundaries.

### Changed

- Controller ownership moved out of the legacy GUI/shared state into a dedicated core service.
- Controller input polling preserves the upstream high-frequency touchpad behavior at 250 Hz while battery/state publication is de-noised.
- Controller connection is now explicitly USB-only; non-USB connections detected by `pydualsense` are rejected.
- Haptics output failures no longer poison deduplication state and are surfaced through diagnostics.
- WASAPI default-output checks are throttled to approximately every two seconds, matching the upstream behavior instead of running per audio chunk.
- Runtime rumble mapping parameters apply without forcing capture restart; filter/envelope structural parameters trigger a controlled rebuild.
- Touchpad and synthetic mouse cleanup now attempts deterministic release after failures, disable, disconnect and shutdown.
- Microphone-button feedback remains on the right motor, preserving upstream behavior.
- Local API binding is restricted to `127.0.0.1`, `::1` or `localhost`.
- REST contracts are strict Pydantic models instead of untyped `dict[str, Any]` bodies.
- Browser-origin WebSocket connections are rejected unless explicitly allowed.
- Bundled profile names are reserved and cannot be silently shadowed by user profiles.
- Health no longer treats a normal "waiting for USB controller" state as service degradation.
- Static typing gate now covers the full `dualsense_companion` package.
- Unused NumPy runtime dependency removed after DSP extraction.
- `build.bat` now requires Python 3.12.x and fails early on unsupported Python versions.

### Preserved from upstream

- USB DualSense connection through `pydualsense`.
- Existing audio-driven rumble tuning and mapping intent.
- WASAPI loopback source selection behavior.
- One-finger pointer movement, tap-to-click, two-finger scroll/tap and L3/R3 mouse behavior.
- Legacy `customtkinter` GUI as a temporary P0 client.
- Default/starter configuration values and presets.
- PyInstaller-based Windows packaging path.

### Safety and scope

- P0 remains wired/USB only.
- No Bluetooth, pairing or wireless transport was added.
- No XInput/virtual controller, HidHide, game detection, auto-profile, remapping system, updater or remote Cloudflare exposure was added.
- The local API cannot bind to external interfaces in P0.

### Validation

- `pytest`: 45 passed.
- Ruff format/lint: PASS.
- mypy full package: PASS, 37 source files.
- stdlib fallback suite: PASS with expected optional-web skips.
- `compileall`: PASS.
- wheel build: PASS.
- source boundary audit: PASS.
- wireless implementation audit: PASS.
- silent operational `except: pass` audit: PASS.
- aggregate automated coverage: approximately 65%.

### Pending physical validation

The following remain explicitly `HARDWARE VALIDATION PENDING`:

- Windows PyInstaller build on Python 3.12.x;
- physical DualSense USB connection/reconnection;
- real WASAPI audio-driven rumble;
- real Windows touchpad/`SendInput` behavior;
- packaged GUI smoke test.
