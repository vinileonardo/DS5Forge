# DS5Forge architecture — P0 foundation through P5 stabilization

P0 keeps the upstream USB behavior while making the local core the only owner
of controller hardware. The legacy GUI and the local API are clients of the
same in-process `CoreFacade`; neither receives a `pydualsense` object.

```text
GUI (customtkinter) ─┐
                     ├─ CoreFacade ─ StateStore/EventBus ─ API + WebSocket
headless/API client ─┘       │
                             ├─ ControllerService ─ platform/windows/dualsense_adapter
                             ├─ HapticsService ─ pure DSP ─ WASAPI adapter
                             └─ TouchpadService ─ gesture interpreter ─ SendInput adapter
                             ├─ ForegroundWorker ─ ForegroundDetector ─ Win32 adapter
                             ├─ GameRegistryRepository ─ games.json
                             ├─ RemappingEngine ─ OutputManager ─ keyboard/mouse adapters
                             ├─ ExclusiveCoordinator ─ fixed Windows helper boundary
                             └─ AdaptiveTriggerEngine ─ native/telemetry/reactive arbitration

Browser Vite SPA ────────────┘
       │ HTTP + WebSocket (validated v1 contracts)
Tauri 2 shell ───────────────┘

Controller Lab (`/controller`) is a client surface only. It renders complete
input snapshots and submits typed lightbar, trigger, haptics, calibration and
gesture commands through `CoreFacade`; it never reaches the adapter directly.
Games (`/games`) is also a client surface only. The core evaluates executable
rules, applies profiles and owns all synthetic output release paths. Its
foreground identity excludes window titles, which are diagnostic context only.
```

The P1 browser and Tauri clients are the same React/TypeScript SPA. Its
`RuntimeProvider` owns one projection of HTTP bootstrap data and validated
WebSocket events, with explicit `online`, `reconnecting`, `offline` and
`protocol_error` states. A WebSocket transport opening is not considered
trusted/online until its mandatory initial `state.snapshot` validates. Pages do
not import Python, `pydualsense`, WASAPI or Windows HID APIs. A lost core marks
the projection stale and never presents it as current controller success.

The Tauri layer is a shell only: it contains one window, a narrow CSP and the
default core window permission. It does not execute processes, own hardware,
bundle a Python sidecar, open a remote endpoint, or implement installer/tray/
updater/autostart behavior. During P1 development the core is started
separately with `python source/run.py --headless`.

P5 keeps the same authority boundary. The fixed Tauri sidecar is a desktop
process supervisor and native `.exe` picker only; the Python core remains the
sole owner of `pydualsense`, WASAPI, Windows HID and synthetic output state.
Exclusive virtualization is capability-gated behind a restricted HIDMaestro
helper protocol. Physical suppression stays in the Windows core through the same
selected-device HidHide authority used by Remap. The UI never imports HIDMaestro,
HidHide or a Windows API.

## Boundaries

- `domain/` contains frozen snapshots, complete normalized input/telemetry,
  game/automation/compatibility contracts, capability availability,
  lab/profile contracts, error codes and event envelopes. It has no Windows,
  GUI or web imports.
- `core/` owns lifecycle, immutable state publication, haptics DSP, gestures,
  config persistence, 250 Hz reads, 30 Hz latest-value telemetry, Controller
  Lab safety coordinators, foreground polling, game automation, remapping,
  synthetic output ownership and the facade.
- `platform/windows/` is the only place that imports `pydualsense`,
  `PyAudioWPatch` or Windows `SendInput`. `platform/windows/composition.py` is
  the Windows composition root that injects those adapters into `CoreFacade`;
  the core never imports a platform implementation. Imports are lazy so Linux/CI can run
  domain and core tests without hardware.
- `platform/windows/exclusive_provider.py` is a fixed HIDMaestro helper boundary.
  It does not silently install a provider, invoke `pythonnet` or run an arbitrary
  shell command. Provenance, signature, hash and Windows validation are explicit
  capability inputs. `platform/windows/hidhide.py` remains the sole physical
  suppression authority and resolves the selected HID path when multiple
  DualSense devices are present.
- `api/` is a presentation adapter. The default server bind is `127.0.0.1`;
  browser HTTP requests with an explicit unapproved `Origin` are rejected
  before reaching the facade, CORS is limited to the same Vite/Tauri
  local-origin allow-list, and WebSocket origin validation uses that same
  policy. No tunnel or remote exposure is started.
- `gui.py` keeps the upstream presentation temporarily, but reads snapshots and
  calls facade commands rather than mutating runtime state.
- `GameRegistryRepository` owns a separate strict/atomic `games.json`. The
  registry is validated before replacing memory or the active remapper.
- `ForegroundWorker` is bounded to 500–1000 ms and interruptible. Adapter
  failures become recoverable observations/diagnostics instead of terminating
  the worker.
- `OutputManager` tracks keyboard/mouse ownership and retains explicit logical/
  virtual extension points. P3 persistence rejects logical output until a real
  production adapter exists. Chord candidates delay simple mappings until all
  overlapping chord windows expire, completed chords win, and every teardown
  path attempts release across all adapters.
- `ExclusiveCoordinator` owns virtual output/passthrough/suppression ordering,
  ownership token, generation, heartbeat and stale recovery. A successful mirror
  refreshes the core lease; a bounded monitor thread sends the provider heartbeat
  at a throttled rate and expires the session when the lease goes stale,
  independent of the controller read callback. The virtual provider returns
  game-authored USB DualSense output reports, while `ControllerService` forwards
  verified report `0x02` packets to the selected physical controller. During
  that session the Windows adapter suppresses pydualsense-generated competing
  writes. Virtualization, feedback passthrough or physical suppression failure
  rolls back the whole transaction; missing suppression keeps
  `double_input_risk=true`. Exclusive refuses to coexist with Remap/Virtual and
  a mode change disables it first.
- `AdaptiveTriggerEngine` is separate from Controller Lab previews. It
  arbitrates `game_native`, `telemetry`, `reactive` and `off` with TTL and
  reset/watchdog ownership. Reactive effects are labeled generated effects and
  are only produced when a game explicitly selects `reactive`; `native` is the
  default and `off` neutralizes DS5Forge output. `game_native` is reserved for
  real virtual-provider output-report feedback. The core forwarding path is now
  implemented, but the HIDMaestro helper remains capability-gated until its
  Windows build/install and hardware validation are complete.

## Lifecycle and teardown

`ControllerService` owns one adapter at a time and publishes
`disconnected → connecting → connected`, then `reconnecting` or `error` when a
USB read/connect attempt fails. Input is sampled at the upstream 250 Hz cadence;
unchanged battery telemetry is not republished at that rate. The Windows adapter
rejects any connection that `pydualsense` reports as non-USB. Backoff is bounded
and interruptible. Stop signals are joined, motors/triggers are neutralized
where supported, haptics is stopped, Controller Lab previews/tests are ended,
and the touchpad service releases synthesized buttons. The telemetry publisher
keeps only the newest input and publishes at most about 30 Hz with monotonic
sequence metadata.

## State and events

`RuntimeSnapshot` and nested contracts are frozen dataclasses. `StateStore`
increments a sequence and publishes versioned envelopes. Subscribers receive a
bounded queue; a slow client cannot block controller workers. WebSocket clients
receive `state.snapshot` first, followed by lifecycle/input/lab/state/audio/
config/profile, game/automation/compatibility and diagnostic events. A reconnect
drops held telemetry so stale input cannot be presented as a fresh connected
sample. Unknown future event types are ignored by the browser client.

## Configuration

Configuration is schema v1. Bundled defaults/profiles under `resources/` are
read-only and their names are reserved case-insensitively; user config/profiles
live in the platform app-data directory and are written atomically. Invalid user
config falls back to validated defaults and surfaces a structured diagnostic.
Controller profiles are schema v2: every section is validated before any
hardware output is touched, legacy rumble-only files migrate in memory, and
unsupported capabilities are returned as explicit sections rather than being
silently sent to hardware.

The haptics service preserves the upstream DSP mapping. Mapping-only settings
are read live without restarting capture; filter/envelope changes rebuild DSP
state, and default-output changes are checked on the upstream ~2-second cadence.

P3 game/automation data is deliberately not merged into schema-v1 `config.json`.
It lives in schema-v2 `games.json`, which supports one-or-more executable
identities per game and migrates the unreleased P3 schema-v1 shape. The default
exit policy is `restore_previous`; Native is the default mode and
Virtual requires a provider with physical suppression. The HIDMaestro helper
source/build pipeline is present, but it remains unavailable at runtime until the
pinned helper is built, the provider is explicitly installed and Windows/hardware
validation passes.

## P2/P3/P5 safety boundaries

- Trigger previews are single-flight and server-TTL-bound; every terminal path
  attempts both-trigger Off reset.
- Haptics test runs are single-flight and bounded; motors are neutralized before
  audio-driven rumble restarts.
- Stick calibration/deadzone is applied only to DS5Forge Exclusive virtual
  mirroring and to visualization/profile metadata. Native game input and the
  authoritative raw telemetry are never rewritten. Remap remains a
  digital keyboard/mouse mapper; there is no remap analog-deadzone path.
- Browser profile import is text-only and size-limited; malformed, oversized,
  incompatible or unconfirmed-overwrite imports leave current state unchanged.
- Game registry updates are all-or-nothing. Mapping/chord ownership is scoped
  by active game, and manual profile/mode changes suspend reapplication in the
  current context until a real foreground transition.
- Process conflict diagnostics are best effort and non-controlling. Steam is
  reported only as a possible configuration-dependent conflict.
- Lightbar RGB intensity is scaled in software and does not reuse Player LED
  brightness. Pulse workers are interruptible and joined during teardown.
- Touch normalization preserves both adapter touch slots, contact IDs and
  bounded raw values for diagnostics. Radial deadzone is applied only for
  remapping/Exclusive behavior; Native values stay raw.

## Explicit P0/P2/P3/P5 exclusions

P0–P4 are USB/wired only. There is no Bluetooth, wireless transport/pairing,
tunnel, installer, updater or new Tauri permission in P3. Virtual/XInput is
modeled but unavailable in production because no approved provider with safe
physical suppression is installed. Windows and physical DualSense USB proof
remain `HARDWARE VALIDATION PENDING`.

P5 does not add Bluetooth, wireless pairing, dongles or ViGEmBus. HIDMaestro
virtualization plus core-owned HidHide suppression is implemented behind strict
gates, but provider installation is still explicit rather than automatic.
Exclusive starts OFF and remains unavailable until provenance, integrity,
signature, virtual output reports, physical feedback passthrough, selected-device
suppression and Windows validation are all proven. See
[`ADR_P5_EXCLUSIVE_INPUT_PROVIDER.md`](ADR_P5_EXCLUSIVE_INPUT_PROVIDER.md).

## P4 productization boundary

The Python `ProductService` composes product contracts around the existing
facade without taking hardware ownership. `CoreSupervisor` models bounded
desktop/core startup, readiness, crash recovery and shutdown; the Tauri shell
uses the same lifecycle vocabulary while tracking the actual sidecar process.
`GuidedDiagnostics`, `RemoteAccessManager`, `CloudflaredManager`, update
metadata validation and Support Bundle generation are independently testable
and fail closed.

The Tauri shell registers single-instance first, then the fixed sidecar shell,
autostart, updater and tray. The bundle target is per-user NSIS. The only
external process path is the packaged headless core with fixed loopback
arguments. Remote Access and cloudflared are disabled until explicitly paired
and configured; the core API never changes from loopback.

P5 adds only the native executable-picker command and keeps Tauri capabilities
least-privilege. Remote Access remains under the existing product boundary and
is presented under Settings → Advanced without changing its security model.
