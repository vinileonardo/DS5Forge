# DS5Forge architecture — P0 foundation + P1 clients + P2 Controller Lab

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

Browser Vite SPA ────────────┘
       │ HTTP + WebSocket (validated v1 contracts)
Tauri 2 shell ───────────────┘

Controller Lab (`/controller`) is a client surface only. It renders complete
input snapshots and submits typed lightbar, trigger, haptics, calibration and
gesture commands through `CoreFacade`; it never reaches the adapter directly.
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

## Boundaries

- `domain/` contains frozen snapshots, complete normalized input/telemetry,
  capability availability, lab/profile contracts, error codes and event
  envelopes. It has no Windows, GUI or web imports.
- `core/` owns lifecycle, immutable state publication, haptics DSP, gestures,
  config persistence, 250 Hz reads, 30 Hz latest-value telemetry, Controller
  Lab safety coordinators and the facade.
- `platform/windows/` is the only place that imports `pydualsense`,
  `PyAudioWPatch` or Windows `SendInput`. `platform/windows/composition.py` is
  the Windows composition root that injects those adapters into `CoreFacade`;
  the core never imports a platform implementation. Imports are lazy so Linux/CI can run
  domain and core tests without hardware.
- `api/` is a presentation adapter. The default server bind is `127.0.0.1`;
  browser HTTP requests with an explicit unapproved `Origin` are rejected
  before reaching the facade, CORS is limited to the same Vite/Tauri
  local-origin allow-list, and WebSocket origin validation uses that same
  policy. No tunnel or remote exposure is started.
- `gui.py` keeps the upstream presentation temporarily, but reads snapshots and
  calls facade commands rather than mutating runtime state.

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
config/profile and diagnostic events. A reconnect drops held telemetry so stale
input cannot be presented as a fresh connected sample.

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

## P2 safety boundaries

- Trigger previews are single-flight and server-TTL-bound; every terminal path
  attempts both-trigger Off reset.
- Haptics test runs are single-flight and bounded; motors are neutralized before
  audio-driven rumble restarts.
- Stick calibration/deadzone is metadata for DS5Forge visualization/profile
  behavior only and never rewrites native game input.
- Browser profile import is text-only and size-limited; malformed, oversized,
  incompatible or unconfirmed-overwrite imports leave current state unchanged.

## Explicit P0/P2 exclusions

P0–P4 are USB/wired only. There is no Bluetooth, wireless transport/pairing,
virtual controller, game detection, tunnel, installer, updater, remapping or
compatibility/emulation implementation in P2.
