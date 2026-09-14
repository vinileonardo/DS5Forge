# DS5Forge P0 architecture

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
```

## Boundaries

- `domain/` contains frozen snapshots, input contracts, error codes and event
  envelopes. It has no Windows, GUI or web imports.
- `core/` owns lifecycle, immutable state publication, haptics DSP, gestures,
  config persistence and the facade.
- `platform/windows/` is the only place that imports `pydualsense`,
  `PyAudioWPatch` or Windows `SendInput`. `platform/windows/composition.py` is
  the Windows composition root that injects those adapters into `CoreFacade`;
  the core never imports a platform implementation. Imports are lazy so Linux/CI can run
  domain and core tests without hardware.
- `api/` is a presentation adapter. The default server bind is `127.0.0.1`;
  CORS is opt-in and no tunnel or remote exposure is started.
- `gui.py` keeps the upstream presentation temporarily, but reads snapshots and
  calls facade commands rather than mutating runtime state.

## Lifecycle and teardown

`ControllerService` owns one adapter at a time and publishes
`disconnected → connecting → connected`, then `reconnecting` or `error` when a
USB read/connect attempt fails. Input is sampled at the upstream 250 Hz cadence;
unchanged battery telemetry is not republished at that rate. The Windows adapter
rejects any connection that `pydualsense` reports as non-USB. Backoff is bounded
and interruptible. Stop signals are joined, motors are neutralized, haptics is
stopped, and the touchpad service releases synthesized buttons.

## State and events

`RuntimeSnapshot` and nested contracts are frozen dataclasses. `StateStore`
increments a sequence and publishes versioned envelopes. Subscribers receive a
bounded queue; a slow client cannot block controller workers. WebSocket clients
receive `state.snapshot` first, followed by lifecycle/state/audio/config/profile
and diagnostic events.

## Configuration

Configuration is schema v1. Bundled defaults/profiles under `resources/` are
read-only and their names are reserved case-insensitively; user config/profiles
live in the platform app-data directory and are written atomically. Invalid user
config falls back to validated defaults and surfaces a structured diagnostic.
Profiles are validated before they reach DSP.

The haptics service preserves the upstream DSP mapping. Mapping-only settings
are read live without restarting capture; filter/envelope changes rebuild DSP
state, and default-output changes are checked on the upstream ~2-second cadence.

## Explicit P0 exclusions

P0 is USB/wired only. There is no Bluetooth, wireless transport/pairing,
virtual controller, game detection, tunnel, new frontend, installer or updater
implementation.
