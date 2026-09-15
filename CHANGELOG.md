# Changelog

All notable changes to DS5Forge will be documented in this file.

The project currently evolves from the upstream `Casliyan/DS5companion` baseline recorded in `UPSTREAM.md`.

## 0.4.0-rc.3 — Release Candidate 3 — 2026-09-15

### Recovery UX hardening

- Keeps desktop-shell recovery controls available when the local core is offline instead of replacing the entire Settings page with a core-dependent empty state.
- `Check for updates`, `Restart core` and autostart remain available independently of core-backed preferences.
- Core-owned Appearance, microphone, Remote Access and Support Bundle actions stay unavailable or disabled while the core is offline.
- Removes source-development instructions from the installed Settings surface and states that the desktop shell manages the packaged core.
- Adds a regression test proving signed updates remain reachable with `config=null` and `coreStatus=offline`.

### Validation intent

- RC1 → RC2 updater UI proof could not be completed because RC1 hid the updater whenever the core was offline; this is recorded as an RC1 recovery UX defect rather than treated as updater success.
- Install RC2 as the corrected runtime baseline, then validate the signed in-app updater end-to-end with RC2 → RC3.

## 0.4.0-rc.2 — Release Candidate 2 — 2026-09-15

### Stabilization fixes from RC1 Windows validation

- Fixed the Rust-side Tauri sidecar lookup to use the embedded binary basename (`ds5forge-core`) so the packaged core actually starts from an installed build.
- Moved the Windows GUI subsystem attribute to the binary entrypoint (`main.rs`), eliminating the visible console window that RC1 opened beside the desktop UI.
- Added a PE subsystem verifier to Windows CI and release workflows so both `ds5forge.exe` and `DS5ForgeCore.exe` must be GUI-subsystem binaries before release publication.
- Removed the duplicated Overview-level core-offline notice and replaced source-development guidance with product recovery guidance (`Settings > Restart Core` / Diagnostics).

### Validation intent

- Keep an installed `0.4.0-rc.1` as the source install for the first real RC updater proof.
- Publish `0.4.0-rc.2` only after CI proves the corrected Tauri build and PE subsystem contract.
- Validate RC1 → RC2 update before continuing the Windows lifecycle, physical USB and Remote Access matrices.

## 0.4.0-rc.1 — Release Candidate 1 — 2026-09-15

### Release hardening

- Promoted previously local Tauri release-contract checks into the committed test suite.
- Fixed updater initialization so the base Tauri config is valid before CI injects the signing public key and endpoint.
- Fixed SemVer prerelease ordering so `rc.1 < rc.2 < 0.4.0` and downgrades are rejected correctly.
- Switched Windows updater artifacts to the native Tauri 2 NSIS `*-setup.exe` + detached `.sig` contract.
- Added separate prerelease/stable updater channels and automated versioned GitHub Release publication from signed tags.
- Extended version validation to cover the npm root lock entry and the DS5Forge package entry in `Cargo.lock`.

### Validation status

- Source/CI gates must be green before the `v0.4.0-rc.1` tag is created.
- Real Windows install/reinstall/upgrade/uninstall, packaged sidecar lifecycle, Remote Access and physical DualSense USB validation remain release-candidate evidence, not inferred from CI.

## Unreleased — P3 Compatibility / Games / Automation — 2026-09-14

### Added

- `/games` UI with foreground executable diagnostics, active-game/profile
  state, automation, exit policy, registry editor, match explanations,
  mappings, chords and conflict warnings.
- Strict schema-v2 `games.json` persistence separate from P2 `config.json`, with multiple executable identities per game and migration from the unreleased P3 schema-v1 shape.
  including atomic writes, recovery to safe in-memory defaults and structured
  validation errors.
- Executable-based auto-profile transitions for game A → game B, game →
  desktop/process exit, manual override and `restore_previous`,
  `apply_default` and `keep_current` policies.
- Versioned P3 HTTP/WebSocket contracts, foreground/process Windows adapters,
  keyboard SendInput ownership, chord precedence/debounce and synthetic
  release reports.
- Explicit Native, Remap and Virtual/XInput capability state with an
  injectable fake provider for tests.

### Safety and scope

- Native remains the default and creates no synthetic output. Remap is opt-in;
  virtual activation is rejected without an approved provider that can safely
  suppress physical input.
- Conflict diagnostics are process-name evidence only. DS5Forge never claims
  Steam Input is active, kills processes or changes external settings.
- P3 remains USB/wired only and adds no Bluetooth/wireless transport, driver,
  installer or new Tauri permission.
- Automated/source-level evidence can be handed to independent review;
  Windows foreground/SendInput, packaged builds and physical DualSense USB
  evidence remain `HARDWARE VALIDATION PENDING`.

## Unreleased — P2 Controller Lab / DualSense Depth — 2026-09-14

### Added

- Controller Lab at `/controller` with Input, Triggers, Lighting and Sticks tabs.
- Complete normalized button, trigger, stick and touch telemetry with bounded
  latest-value WebSocket publication at approximately 30 Hz over the core's
  250 Hz USB read cadence.
- Capability-aware lightbar and adaptive-trigger contracts, server-TTL trigger
  previews, single-flight haptics test bench and DS5Forge-only stick metadata.
- Schema-v2 full controller profiles with legacy rumble-only migration,
  atomic writes, strict browser import/export and explicit overwrite confirmation.
- Python, frontend and facade safety tests for normalization, capability
  gating, bounded queues, neutralization, profile rejection and stale UI state.

### Changed

- Touchpad settings now expose gesture controls and the Controller Lab shows
  live touch points/button state while preserving core-owned mouse behavior.
- Adapter/library capability detection disables unsupported output paths and
  returns structured reasons instead of assuming published optional surfaces.

### Fixed

- Realtime trust now stays stale while the WebSocket transport is online but the
  latest validated snapshot reports a disconnected controller, and command
  responses no longer force `stale: false` for a disconnected runtime.
- Haptics, Touchpad and Settings drafts preserve unsaved edits across config
  refresh/reconnect and rejected saves by syncing from config only when the
  draft is not dirty, avoiding update/save effect loops.
- Runtime capability counting ignores the `availability` object, and profile
  overwrite confirmation uses task-specific busy wording instead of delete
  wording.

### Safety and scope

- Trigger previews and haptics tests always have bounded stop paths; disconnect,
  reconnect, profile apply, adapter failure and shutdown attempt neutral output.
- P2 remains USB/wired only. No Bluetooth, wireless transport/pairing, virtual
  controller, game detection, remapping or compatibility layer was added.
- Physical Windows + wired DualSense evidence remains
  `HARDWARE VALIDATION PENDING`; no final hardware GO is declared.

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
