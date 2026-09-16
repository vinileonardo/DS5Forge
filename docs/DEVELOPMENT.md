# P0–P5 development and verification

Python 3.12.x is the required P0 development/build runtime. From the repository root:

```text
python -m venv .venv
python -m pip install -e ".[dev]"
ruff format source tests
ruff check source tests
mypy source/dualsense_companion
pytest
python -m compileall -q source tests
python -m build --wheel
python scripts/validate_versions.py --expected 0.4.0-rc.8
```

Headless core/API and the retained GUI are separate entry modes:

```text
python source/run.py --headless
python source/run.py
```

The GUI/API share one `CoreFacade` in the desktop process. Use injected fake
controller, capture, foreground, process, keyboard and virtual-provider
adapters for tests; do not boot Bluetooth, wireless transports or production
virtual-controller software.

## P1/P2 frontend

Node.js 20+ and npm are required for the web client. The browser client is
served separately from the Python authority during development:

```text
# terminal 1, repository root
python source/run.py --headless

# terminal 2
cd frontend
npm ci
npm run dev
```

The Vite server uses `127.0.0.1:5173`; preview uses `127.0.0.1:4173`.
The Python API accepts only those explicit local browser origins and
`http://tauri.localhost`; browser HTTP requests carrying any other `Origin`
are rejected before reaching API handlers. The API bind remains loopback-only
and no URL query parameter or cloud endpoint can override the frontend base URL.

Frontend verification commands:

```text
cd frontend
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
npm run e2e
npm audit --omit=dev
```

Tauri 2 local native development is optional. It is not required for Python
core work or for the browser SPA. The `tauri-windows` CI job is the canonical
native-Windows compile gate and provisions Node and Rust in the runner.

To run/build the desktop shell locally on Windows, install Node.js LTS and
Rust on the Windows host, select the `stable-msvc` Rust toolchain, and ensure
Visual Studio Build Tools includes the **Desktop development with C++**
workload. WebView2 is also required by Tauri and is normally already present
on current Windows 10/11 installations.

Recommended PowerShell bootstrap when local native development is actually
needed:

```text
winget install --id OpenJS.NodeJS.LTS -e
winget install --id Rustlang.Rustup -e
# reopen PowerShell
rustup default stable-msvc
node --version
npm --version
rustc --version
cargo --version
```

Then run `npm ci` and `npm run tauri:dev` or `npm run tauri:build` from
`frontend/` in a Windows-accessible checkout. Do not add Linux WebKitGTK or a
cross-compilation stack merely to validate the Windows shell from WSL unless
Windows/CI builds are unavailable; native Windows compilation is the preferred
path.

`npm run tauri:build` invokes the normal frontend production build through
Tauri's `beforeBuildCommand`, so it does not depend on a stale pre-existing
`dist/`. The P1-P3 browser/Tauri development contract was intentionally thin;
the P4 Windows bundle adds only the explicitly scoped sidecar, process/shell,
installer, updater, tray and autostart integrations documented in the P4 ADRs.

The PyInstaller baseline remains available on Windows. `source/build.bat` validates that the active interpreter is Python 3.12.x before installing/building:

```text
cd source
build.bat
```

The P2 Controller Lab is at `/controller` and has Input, Triggers, Lighting and
Sticks tabs. Keep the route usable while offline, but disable output commands
until the core reports a fresh connected USB snapshot. Browser imports use
`File.text()` and the API's 64 KiB limit; do not add filesystem, shell or
process permissions to Tauri.

P2 API/profile checks should include strict unknown-field/coercion/non-finite
rejection, capability-disabled no-call behavior, trigger timeout/cancel and
reconnect neutralization, bounded haptics tests, full-profile validation before
apply, atomic writes and state-preserving rejected imports.

## P5 compatibility and UX checks

The P5 source gates are recorded in [`P5_VALIDATION.md`](P5_VALIDATION.md).
Exclusive tests must use injected deterministic providers and must assert that
the default capability is unavailable, failed suppression rolls back virtual
state, watchdog expiry exposes physical input and duplicate-input risk, and
ownership tokens never leave the core. Do not install HIDMaestro, HidHide or a
driver during a Linux test run.

Adaptive trigger tests must exercise native > telemetry > reactive arbitration,
TTL expiry, coalescing and Off reset, and facade-level per-game
`native`/`reactive`/`off` behavior driven from the real audio envelope and
current input. `game_native` is reserved for real virtual-provider
output-report feedback, which is not implemented in this source; do not invent
telemetry at that priority. Lightbar tests must keep RGB intensity independent
from Player LED intensity, prove `enabled` maps to zero output while preserving
saved RGB, and stop the single authoritative software pulse worker before
adapter teardown. Calibration tests must prove Exclusive mirroring receives
calibrated sticks while Native telemetry stays raw. Touch tests must use both
`trackPadTouch0` and `trackPadTouch1` fields from the pinned pydualsense
surface.

The Games picker is presentation-tested with a mocked Tauri invoke and a
browser `.exe` fallback. Running/recent candidates remain non-persistent until
the user saves. Stale runtime values are historical context only. Locale key
parity and Dark/theme first paint are tested without network access.

## P5.1 Windows Live Dev Bridge

When the checkout runs under WSL on the same Windows machine as the installed
DS5Forge build, use the development-only bridge to inspect the live loopback
runtime without exposing a new listener:

```text
./.venv/bin/python scripts/windows_live_bridge.py snapshot
./.venv/bin/python scripts/windows_live_bridge.py api state
./.venv/bin/python scripts/windows_live_bridge.py processes
./.venv/bin/python scripts/windows_live_bridge.py dualsense
./.venv/bin/python scripts/windows_live_bridge.py hidhide
./.venv/bin/python scripts/windows_live_bridge.py ws --count 5 --timeout 5
```

The bridge reads the existing `127.0.0.1:8765` HTTP/WebSocket surface and uses
PowerShell only for read-only Windows process/PnP/HidHide inspection. It does
not change firewall rules, bind a port, install a driver or enable remote
access. `processes` reports the parent/child process tree because a PyInstaller
one-file sidecar normally appears as a bootloader process plus its child
application process; those rows are not automatically evidence of two
independent cores.

P5.1 physical-input isolation is separate from Exclusive virtual-controller
ownership. In Remap, an already installed HidHide may explicitly hide the
currently connected wired DualSense while allowlisting the packaged
`ds5forge-core.exe`. The operation is transactional, records only DS5Forge-owned
changes for rollback/recovery and never installs HidHide. Native stays the
default. HIDMaestro/output-report Exclusive remains unavailable until its own
provider gates and Windows evidence are complete.

## P3 Games / automation checks

The Games page is at `/games`. Add rules with one or more executable names,
review each explanation, then enable automation. The core must demonstrate A → B, game →
desktop and process-exit transitions, previous-profile capture, all exit
policies, manual override and no reapply inside an unchanged context. Mappings
and chords are validated before activation; keyboard targets may be bounded
`+` combinations with shared-key ownership, chord candidates delay simple
outputs during a bounded window and all synthetic outputs release on every
transition/exception/disconnect/shutdown.

Virtual/XInput is an explicit unavailable state in this sprint. A request for
it must return a structured error and leave the previous mode unchanged.
Conflict diagnostics may report Steam/remappers by process name, but must not
claim active interception or control another process. `games.json` is separate
from P2 config, schema-v2, atomically written and migrates the unreleased P3
schema-v1 single-executable shape.

Run the complete P3 evidence record in [`P3_VALIDATION.md`](P3_VALIDATION.md).

## Gate recording

- Format/lint/static checks: run in CI and record the exact command/result.
- Unit/integration tests: run without a controller; hardware adapters are
  tested by import/package checks and manual Windows USB smoke evidence.
- API smoke: use the FastAPI test client or loopback server and record health,
  state, config validation and command responses.
- WebSocket smoke: record initial snapshot, a state event and reconnect.
- USB checklist: complete `docs/D0_SMOKE_CHECKLIST.md` on Windows with a real
  cable/controller. Linux/CI results must remain `HARDWARE VALIDATION PENDING`.
- P2/P3 evidence: record separate automated Linux, frontend, Windows build,
  physical USB and limitation sections in `docs/P2_VALIDATION.md`; automated
  green tests do not substitute for physical DualSense evidence. P3-specific
  results belong in `docs/P3_VALIDATION.md`. P5 provider, Windows and physical
  evidence belongs in `docs/P5_VALIDATION.md`; automated green tests do not
  replace `WINDOWS/HARDWARE VALIDATION PENDING`.

## P4 productization commands

```text
python3 scripts/validate_versions.py
python3 scripts/build_core.py                 # Python 3.12 + PyInstaller
python3 scripts/prepare_sidecar.py            # Windows target-triple copy
python3 scripts/build_desktop.py              # SPA build
python3 scripts/build_desktop.py --tauri      # SPA + Tauri bundle
python3 scripts/build_installer.py            # NSIS; no signing key required
python3 scripts/build_installer.py --release  # requires CI-only signing keys
python3 scripts/generate_checksums.py <dir>
python3 scripts/generate_release_metadata.py --signature <text> --url <https-url>
```

`VERSION` is canonical. Release scripts never print or persist signing key
material. The tagged Windows workflow builds signed updater artifacts, uploads
the CI artifact bundle and publishes the matching GitHub Release. Prerelease
builds embed the fixed `update-rc` metadata endpoint; stable builds embed
GitHub's `releases/latest` endpoint. The workflow refreshes `update-rc` for each
RC and once again for the stable release so RC installs can upgrade into the
final version. `cloudflared` must be installed/configured by the user; no script
downloads or updates it.
