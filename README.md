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
are intentionally kept close to the upstream behavior. Adaptive-trigger labs,
lightbar tooling, game detection, auto-profiles, virtual/XInput compatibility
and broader remapping belong to later sprints.

That means the biggest P0 benefit during normal play should be **reliability**,
not a dramatically different controller feel: cleaner reconnect behavior,
safer shutdown/disconnect, fewer chances of stuck synthetic mouse buttons,
validated configuration and better recovery/diagnostics when audio or hardware
fails. Physical Windows + DualSense USB validation is still required before we
claim regression-free hardware behavior.

## Developer setup

Python 3.12.x is the required P0 development/build runtime:

```text
python -m venv .venv
python -m pip install -e ".[dev]"
pytest
```

Run the retained GUI with `python source/run.py`, or run the same core/API
without a GUI with `python source/run.py --headless`. The P0 API is strictly
loopback-only (`127.0.0.1`, `::1` or `localhost`). Physical USB validation remains recorded separately as
`HARDWARE VALIDATION PENDING` until the Windows checklist is executed.

## Roadmap

See [`docs/D0_BASELINE_AND_ROADMAP.md`](docs/D0_BASELINE_AND_ROADMAP.md).

The planned delivery is split into five large sprints:

- **P0** — Foundation / Core Authority
- **P1** — PC-first UX / Web + Desktop
- **P2** — Controller Lab / DualSense Depth
- **P3** — Compatibility / Games / Automation
- **P4** — Productization / Release / Remote Control

## Upstream and license

DS5Forge is derived from `Casliyan/DS5companion`, originally released under the MIT License.

Original copyright notice and license terms must be preserved in all substantial portions derived from the upstream project. See `LICENSE` and `NOTICE.md`.
