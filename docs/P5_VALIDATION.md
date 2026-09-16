# P5 validation — Compatibility, Game Intelligence and UX Stabilization

Version target: `0.4.0-rc.7`
Scope: USB/wired DualSense only.
Review boundary: automated/source-level evidence is separate from Windows and
physical-hardware evidence.

## Automated gates

Run from the repository root:

```text
./.venv/bin/ruff check source tests
./.venv/bin/ruff format --check source tests
./.venv/bin/mypy source
./.venv/bin/python -m compileall -q source tests
./.venv/bin/pytest -q
python3 scripts/validate_versions.py --expected 0.4.0-rc.7
git diff --check
```

Frontend gates:

```text
cd frontend
npm ci
npm run format:check
npm run lint
npm run typecheck
npm test -- --run
npm run build
npm audit --omit=dev
```

Native gates must be run with the stable Windows/MSVC toolchain:

```text
cd frontend/src-tauri
cargo fmt --check
cargo check --all-targets --all-features
cargo clippy --all-targets --all-features -- -D warnings
```

Current source-pass results:

- Python/source: `git diff --check`, Ruff check/format, mypy and compileall PASS;
  full pytest: **174 passed**; version validation: `0.4.0-rc.7` PASS.
- Frontend: clean `npm ci`, Prettier, ESLint, TypeScript, **55 Vitest tests**,
  Vite build and `npm audit --omit=dev` PASS with **0 vulnerabilities**.
- Playwright: **11 passed**.
- Windows Rust toolchain was discovered (`cargo.exe`/`rustc.exe`) and
  `cargo fmt --check` PASSed against the Tauri crate. `cargo check` then hit a
  Windows/WSL UNC incremental-lock limitation; the follow-up attempt with a
  Windows-local `CARGO_TARGET_DIR` could not start because WSL interoperability
  itself failed (`UtilAcceptVsock: accept4 failed 110`, including trivial
  `cmd.exe`/PowerShell calls). Therefore `cargo check` and `cargo clippy` remain
  **environment-blocked, not claimed PASS** in this source pass.

## P5 automated coverage

- Exclusive enable ordering, rollback, ownership generation, lease refresh only
  on successful mirroring, public/provider heartbeat isolation, throttled
  provider heartbeat, watchdog expiry,
  stale-recovery reporting (no event when nothing was recovered),
  mirroring/coalescing, duplicate-input risk, disconnect/shutdown idempotency
  and Remap-vs-Exclusive exclusion;
- Exclusive sidecar finite request timeout, stderr pipe-deadlock avoidance and
  `finally` process termination even when the release request fails;
- adaptive trigger arbitration (`game_native` → `telemetry` → `reactive` →
  `off`), TTL, coalescing, generated-effect labeling and reset, plus
  facade-level per-game `native`/`reactive`/`off` behavior, real audio-envelope
  driven effects, game-exit/TTL reset and `adaptive_trigger.changed` emission;
- bounded robust calibration, outlier rejection, Exclusive-mirror application
  and raw Native telemetry preservation;
- RGB intensity/off/pulse teardown (one authoritative software pulse
  mechanism), pydualsense `LedOptions` update-bit reconciliation, and separate
  Player LED state with its own intensity control so RGB changes cannot
  re-enable disabled Player LEDs and Player LED changes cannot extinguish RGB;
- both real pydualsense touch fields (`trackPadTouch0` and `trackPadTouch1`),
  contact IDs and raw diagnostics;
- deterministic audio bytes through the normal playback/loopback/DSP path to
  motor output and neutralization;
- running/recent game candidates and path/name deduplication;
- `pt-BR`/`en-US` translation key parity, offline persistence, safe storage
  fallback and an app-global provider that updates mounted Games/Settings
  primary and advanced surfaces from a single live locale switch;
- stale topbar/Games projections, profile dropdown, capability-gated Exclusive
  controls that are actionable only when the complete capability is
  operational, running/recent candidate application, browser picker
  identity-only fallback (`executable_path=null`), updater states and Advanced
  Remote Access placement.

Controlled Playwright evidence must mock the local core/API and must not boot a
Bluetooth transport, an emulator, Appium or a production provider. It verifies
presentation contracts only; it does not prove hardware behavior.

## Windows and physical evidence still required

The following are not inferred from Linux tests, source inspection or a fake:

- signed/provenanced HIDMaestro + HidHide helper installation and fixed hash;
- real virtual output reports and full-state mirroring;
- real HidHide session suppression, duplicate-input behavior and recovery after
  helper crash, parent death, Core restart, Quit, updater and uninstall;
- real Windows game launch/foreground matching and Native/Exclusive/Remapping
  behavior;
- native adaptive-trigger output, real virtual-provider output-report feedback
  for the `game_native` priority (not implemented in this source), reactive
  effects on real hardware and physical TTL behavior;
- physical lightbar intensity/effect, Player LEDs and interruptible pulse;
- two simultaneous touch contacts/finger IDs and gesture teardown;
- WASAPI loopback from the actual default output into DSP-driven rumble;
- packaged Tauri sidecar, least-privilege capabilities, PE verification,
  installer lifecycle and signed updater relaunch.

Current handoff status: **WINDOWS/HARDWARE VALIDATION PENDING**. This is a
validation boundary, not a claim of failure in the automated source tests.
