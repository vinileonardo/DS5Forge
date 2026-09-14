# DS5Forge — P2 Execution Pack

## Sprint

P2 — Controller Lab / DualSense Depth

## Goal

Extend the P0/P1 wired core with an observable Controller Lab for input
telemetry, lightbar output, adaptive-trigger experiments, stick metadata and a
bounded haptics test bench. Python remains the only authority for controller
state and output. The browser and Tauri shell remain clients of the versioned
local API.

## Binding constraints

- P0–P4 are USB/wired only. No Bluetooth, pairing, wireless transport,
  dongles or wireless-specific tuning is part of this sprint.
- `pydualsense` remains optional at development time and stays in
  `>=0.7.5,<0.8` on Windows.
- Capability detection is based on the installed adapter/library surface. An
  absent or incomplete surface is reported as unavailable; it is never
  assumed and never called from an unsupported path.
- `pydualsense`, Windows HID and WASAPI names remain inside
  `platform/windows/`.
- Native DualSense behavior remains the default. P2 does not add remapping,
  keyboard mappings, virtual controllers, game detection or compatibility
  modes.

## Workstreams

### A — Domain and transport contracts

Add frozen contracts for complete digital/analog input, touch points, stick
telemetry, lightbar state, trigger effects/previews, haptics test runs,
capability availability and schema-v2 controller profiles. Controller reads
remain approximately 250 Hz for touchpad behavior. `controller.input` is a
latest-value stream decimated to at most 30 Hz with sequence and timestamp
metadata. Subscriber queues are bounded and no telemetry history is retained.

### B — Windows adapter

Map the available `pydualsense` state fields and output objects into domain
contracts. Lightbar, trigger and haptics operations have typed platform-neutral
ports. Adapter failures become structured `DS5ForgeError` values. No raw
library object or enum crosses the adapter boundary.

### C — Safe lab services

The core owns current lab state and applies validated commands. Trigger
previews have a server-side TTL. Timeout, explicit cancel, disconnect,
reconnect, shutdown, adapter failure and profile apply reset both triggers to
Off. Haptics bench runs are bounded, single-flight and neutralized on every
exit; audio-driven rumble is paused and resumed deterministically around a
bench run.

### D — Profile v2

Existing rumble-only files migrate in memory to a full profile without losing
values. Bundled names remain case-insensitively reserved and read-only. Full
profile writes are atomic and validate every section before output is touched.
Unsupported hardware sections are reported explicitly. Browser import sends
JSON text only, with a strict byte limit and explicit overwrite confirmation.

### E — Controller Lab UI

Add `/controller` with internal Input, Triggers, Lighting and Sticks tabs.
Input shows buttons, D-pad, analog triggers, two stick planes and up to two
touch points, with a clear stale/offline state. Trigger and light controls are
capability-gated and show pending/timeout states. Stick calibration/deadzone is
metadata for DS5Forge visualization/profile behavior only; it does not alter
native game input.

### F — Evidence and documentation

Update README, changelog, API, architecture, development guidance and the USB
smoke checklist. `docs/P2_VALIDATION.md` separates Linux automation, frontend,
Windows build, physical DualSense USB evidence and known limitations. Keep
`HARDWARE VALIDATION PENDING` unless physical evidence is actually recorded.

## Required automated coverage

Python tests cover input normalization, optional fields, capability detection,
30 Hz/latest-value behavior, bounded queues, lightbar/trigger validation and
reset paths, haptics bench timeout/lock/neutralization, profile migration and
atomic persistence, import rejection, unsupported sections and touchpad
teardown. Frontend tests cover strict schemas, unknown events, visualizers,
capability gating, pending state and profile import/export. E2E scenarios cover
live input, trigger timeout, lightbar reset, disconnect safety, full profile
apply, rejected import state preservation and reconnect without reload.

## Gate

Run the P0/P1 gates plus Ruff, mypy, pytest, compileall, wheel build, clean
`npm ci`, Prettier, ESLint, TypeScript, Vitest, Vite, Playwright, npm audit,
Cargo format and Tauri configuration/build checks. Run wired-only and boundary
audits. This sprint may hand off `READY FOR INDEPENDENT VALIDATION` but does
not self-declare a physical hardware GO.
