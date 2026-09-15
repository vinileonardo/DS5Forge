# DS5Forge

DS5Forge is a Windows-first DualSense companion focused on making the controller feel first-class on PC while preserving native game support whenever possible.

The project starts from the open-source [`Casliyan/DS5companion`](https://github.com/Casliyan/DS5companion) baseline and evolves it into a more robust architecture with a local controller core, real-time API/WebSocket layer, modern PC-first UI, desktop packaging, profiles, diagnostics, deeper DualSense controls and game-aware automation.

## Current scope

**USB / wired only for P0–P4.** Bluetooth and other wireless transports are intentionally deferred.

## Product direction

- excellent Windows desktop experience;
- browser-accessible UI backed by the same local core;
- responsive mobile control surface when accessing the local instance remotely;
- real-time state over WebSockets;
- optional secure remote access through Cloudflare Tunnel;
- preserve native DualSense behavior by default;
- compatibility/emulation features must be explicit opt-in modes;
- strong diagnostics, reconnect behavior and safe teardown.

## Baseline capabilities inherited from upstream

- DualSense USB connection through `pydualsense`;
- Windows WASAPI loopback capture;
- audio-driven rumble;
- touchpad mouse control and basic gestures;
- profiles/configuration;
- Windows desktop GUI and PyInstaller build flow.

The legacy baseline is preserved behind the P0 core facade. P0 keeps the
customtkinter window as a temporary client while adding a headless core, local
HTTP/WebSocket contracts, deterministic lifecycle, diagnostics and automated
tests. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
[`docs/API.md`](docs/API.md), [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) and
[`CHANGELOG.md`](CHANGELOG.md).

P2 adds the browser Controller Lab at `/controller`. Its Input, Triggers,
Lighting and Sticks tabs consume normalized snapshots and versioned commands;
the Python core remains the only owner of DualSense hardware. Adaptive
triggers and optional lightbar controls are capability-gated from the
installed Windows adapter surface, and every preview/test output has a
server-owned stop or timeout path.

P3 adds the Games surface at `/games`. It matches foreground applications by
one or more configured executable identities, applies profiles through the core,
and exposes explicit Native and Remap behavior plus a diagnosed-but-unavailable
Virtual/XInput model. Game registry, automation policy, mappings and chords are
stored in a separate validated schema-v2 `games.json`. Keyboard mappings support
single keys or bounded combinations such as `CTRL+SHIFT+S`. Foreground polling,
keyboard/mouse output and process
inspection remain behind platform adapters; the UI receives only snapshots and
versioned events. P3 adds no Bluetooth/wireless path, driver, installer,
external-process control or Tauri permission.

## DS5Companion original vs. DS5Forge P0

DS5Forge P0 starts from the upstream snapshot recorded in `UPSTREAM.md`
(`Casliyan/DS5companion`, commit `0a77920cf9a59d2655f6f9915197ead3cbda08e0`).
The objective of P0 is deliberately architectural: preserve the useful wired
behavior while replacing shared mutable hardware state with a reliable core
that later sprints can extend safely.

| Area | Original DS5Companion | DS5Forge P0 |
| --- | --- | --- |
| Controller ownership | GUI/runtime state exposes the `pydualsense` object | Dedicated core owns the hardware; GUI/API receive snapshots and commands |
| Transport | Uses the connection selected by `pydualsense` | Explicitly accepts USB only and rejects non-USB connections |
| Connection lifecycle | Background reconnect loop with broad exception handling | Explicit lifecycle states, bounded backoff, diagnostics and deterministic cleanup |
| Touchpad input | Direct polling + direct Windows `SendInput` | 250 Hz semantic gesture processing separated from the Windows output adapter |
| Synthetic mouse safety | Limited cleanup on failures | Best-effort release on failure, disable, disconnect and shutdown |
| Audio-driven rumble | WASAPI + DSP coupled to runtime state | Same tuning intent split into testable DSP, capture and motor-output layers |
| Audio device changes | Periodic WASAPI output check | Controlled periodic check and capture rebuild without restarting the whole app |
| Configuration | Mutable JSON config | Schema-v1 validation, atomic persistence and safe fallback |
| Profiles | Bundled presets copied into writable user storage | Bundled presets remain immutable; user profiles are stored separately |
| Runtime state | Shared mutable `AppState` | Frozen snapshots with sequence/version and bounded events |
| API | None | Local-only REST `/api/v1` with strict typed contracts |
| Realtime | None | Versioned WebSocket with initial snapshot and bounded backpressure |
| Headless mode | GUI-centric | Core/API can run without the GUI |
| Health/diagnostics | Status strings and swallowed operational errors | Structured health, subsystem state and stable error codes |
| Tests/CI | Minimal/no architectural regression suite | Automated lifecycle, DSP, touchpad, API, WebSocket and boundary tests plus CI |
| Packaging runtime | Environment-dependent Python | P0 development/build target is explicitly Python 3.12.x |

### What P0 intentionally does not change

P0 is not a haptics-quality or game-feature sprint. The audio-driven rumble
mapping, filter/envelope tuning, touch gestures and microphone-button feedback
are intentionally kept close to the upstream behavior. Game detection,
auto-profiles, virtual/XInput compatibility and broader remapping belong to
later sprints; P2's profile and Controller Lab features do not add them.

That means the biggest P0 benefit during normal play should be **reliability**,
not a dramatically different controller feel: cleaner reconnect behavior,
safer shutdown/disconnect, fewer chances of stuck synthetic mouse buttons,
validated configuration and better recovery/diagnostics when audio or hardware
fails. Physical Windows + DualSense USB validation is still required before we
claim regression-free hardware behavior.

## P3 developer setup

Python 3.12.x is the required P0 development/build runtime:

```text
python -m venv .venv
python -m pip install -e ".[dev]"
pytest
```

Run the retained GUI with `python source/run.py`, or run the same core/API
without a GUI with `python source/run.py --headless`. The P0 API is strictly
loopback-only (`127.0.0.1`, `::1` or `localhost`). Physical USB validation
remains recorded separately as `HARDWARE VALIDATION PENDING` until the Windows
checklist is executed. See [`docs/P2_VALIDATION.md`](docs/P2_VALIDATION.md) for
the split automated and physical evidence gate.

P1 makes the browser/Tauri SPA the primary presentation path while keeping the
`customtkinter` GUI as a fallback. In two terminals, start the headless core
and frontend:

```text
python source/run.py --headless
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. The frontend talks only to the local versioned
HTTP/WebSocket contracts; it never receives a controller object or Windows API
handle. P2's Controller Lab uses the same local authority and does not bundle
the Python core or add an installer, tray, updater or autostart path.

P3's Games page uses the same local authority. Enable automation only after
adding executable-identity rules and reviewing the exit policy. `restore_previous` is
the default; a manual profile or mode change is shown as a manual override.
Virtual/XInput remains unavailable unless a future approved provider is
injected and reports reliable physical suppression. See
[`docs/P3_EXECUTION_PACK.md`](docs/P3_EXECUTION_PACK.md),
[`docs/P3_UX_SPEC.md`](docs/P3_UX_SPEC.md) and
[`docs/P3_VALIDATION.md`](docs/P3_VALIDATION.md).

### Optional native Tauri development on Windows

The Rust/Windows native toolchain is **not required** to work on the Python
core or the browser SPA. The `tauri-windows` GitHub Actions job is the
canonical native-Windows compile gate and installs Node and Rust on the CI
runner automatically.

Only developers who want to run or build the Tauri desktop shell locally on
Windows need the native prerequisites:

- Node.js LTS and npm on the **Windows host**;
- Rust installed with `rustup`, using the `stable-msvc` toolchain;
- Microsoft Visual Studio Build Tools with the **Desktop development with C++** workload;
- Microsoft Edge WebView2 Runtime (normally already present on current Windows 10/11 installations).

Recommended Windows PowerShell setup when local Tauri development is actually
needed:

```powershell
winget install --id OpenJS.NodeJS.LTS -e
winget install --id Rustlang.Rustup -e
```

Open a new PowerShell session after installation, then verify/select the MSVC
toolchain:

```powershell
node --version
npm --version
rustup default stable-msvc
rustc --version
cargo --version
```

Then, from a Windows-accessible checkout of the repository:

```powershell
cd frontend
npm ci
npm run tauri:dev
# or
npm run tauri:build
```

Do not install Linux WebKitGTK/Rust dependencies merely to validate the Windows
shell from WSL. Native Windows builds should run on Windows or on the existing
Windows CI job; Tauri documents Linux-to-Windows cross-compilation as a more
complex fallback rather than the preferred workflow.

Useful frontend gates from `frontend/` are `npm run format:check`,
`npm run lint`, `npm run typecheck`, `npm test`, `npm run build` and
`npm run e2e`.

## Roadmap

See [`docs/D0_BASELINE_AND_ROADMAP.md`](docs/D0_BASELINE_AND_ROADMAP.md).

P4 productization contracts and evidence are documented in
[`docs/P4_EXECUTION_PACK.md`](docs/P4_EXECUTION_PACK.md),
[`docs/P4_UX_SPEC.md`](docs/P4_UX_SPEC.md) and
[`docs/P4_VALIDATION.md`](docs/P4_VALIDATION.md). The desktop shell owns the
packaged headless core sidecar, tray, single-instance, optional autostart, NSIS
bundle and signed-updater boundary. Remote Access remains OFF by default; the
local API remains loopback-only and cloudflared is never managed silently. The
canonical version is in [`VERSION`](VERSION).

The planned delivery is split into five large sprints:

- **P0** — Foundation / Core Authority
- **P1** — PC-first UX / Web + Desktop
- **P2** — Controller Lab / DualSense Depth
- **P3** — Compatibility / Games / Automation
- **P4** — Productization / Release / Remote Control

## Upstream and license

DS5Forge is derived from `Casliyan/DS5companion`, originally released under the MIT License.

Original copyright notice and license terms must be preserved in all substantial portions derived from the upstream project. See `LICENSE` and `NOTICE.md`.
