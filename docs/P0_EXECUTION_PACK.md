# DS5Forge — P0 Execution Pack

## Sprint

P0 — Foundation / Core Authority

## Goal

Refactor the upstream DS5Companion baseline into a maintainable local core with explicit hardware lifecycle, typed state/contracts, local HTTP API, realtime WebSocket events, structured diagnostics and automated tests — while preserving the existing USB haptics and touchpad behavior.

P0 is architectural. It is not the sprint for a new polished frontend, Bluetooth, game automation or broad feature expansion.

## Mandatory preconditions

Before implementation:

1. Read `AGENTS.md`.
2. Read `docs/D0_BASELINE_AND_ROADMAP.md`.
3. Read `docs/D0_SMOKE_CHECKLIST.md`.
4. Preserve the upstream MIT attribution.
5. Import/preserve the relevant `Casliyan/DS5companion` source baseline before functional refactoring.
6. Work from a dedicated P0 branch/worktree if Git is available.

## Hard exclusions

Do not implement:
- Bluetooth;
- wireless transports/pairing;
- Pico/dongle support;
- game process detection;
- auto-profile by game;
- XInput/virtual controller;
- HidHide integration;
- remapping/chords beyond behavior already present upstream;
- polished final frontend;
- updater/installer productization;
- Cloudflare remote exposure beyond documenting future integration boundaries.

## Architectural target for P0

Suggested logical boundaries (names may vary if the same separation is maintained):

```text
src/
  ds5forge/
    domain/
      models/
      events/
      errors/
      ports/
    core/
      controller_service.py
      haptics_service.py
      touchpad_service.py
      profile_service.py
      state_store.py
    platform/
      windows/
        dualsense_adapter.py
        wasapi_capture.py
        mouse_output.py
    api/
      http.py
      websocket.py
      schemas.py
    diagnostics/
      logging.py
      health.py
    app.py
```

Do not force this exact tree if the existing code suggests a simpler equivalent. The important requirement is dependency direction: domain/core must not depend on the GUI or web frontend, and platform-specific APIs stay behind adapters.

## Workstream A — Baseline import and provenance

- Preserve upstream source in the repository history.
- Keep `LICENSE` and `NOTICE.md` correct.
- Remove committed compiled `.exe` from the maintained source tree unless there is a strong reason to keep it.
- Preserve/port built-in profiles and default config.
- Record upstream commit SHA used as P0 baseline.
- Add `UPSTREAM.md` with repository, commit, date and imported paths.

Acceptance:
- a reviewer can identify exactly which upstream snapshot P0 started from;
- source can be installed from a clean environment;
- no binary artifact is required to understand/build the code.

## Workstream B — Domain contracts and state

Replace loosely shared mutable runtime state with explicit contracts.

Model at minimum:
- controller connection lifecycle;
- controller identity/capabilities available through current USB library;
- battery/telemetry when available;
- rumble enabled state;
- touchpad enabled state;
- active profile/config version;
- audio capture state/device;
- latest recoverable/unrecoverable error;
- service health.

Recommended connection states:
- `disconnected`;
- `connecting`;
- `connected`;
- `reconnecting`;
- `stopping`;
- `error`.

Requirements:
- UI/API readers consume snapshots rather than mutable hardware objects;
- controller object stays inside infrastructure/core ownership;
- state transitions are testable without real hardware;
- thread/task boundaries are explicit.

## Workstream C — Controller lifecycle

Refactor `ControllerManager` behavior into a deterministic service.

Requirements:
- start without controller attached;
- detect/connect USB controller;
- expose transition states;
- reconnect after cable removal/reinsert;
- bounded backoff rather than scattered arbitrary sleeps where practical;
- clean stop signal;
- neutralize rumble/output on disconnect/shutdown when possible;
- one owner of the hardware connection;
- expected connection failures are not treated as opaque exceptions.

Do not add Bluetooth-specific discovery.

## Workstream D — Haptics engine extraction

Preserve the current WASAPI-loopback-to-rumble behavior first, then improve testability.

Extract deterministic DSP pieces from I/O:
- filters;
- envelope following;
- transient calculation;
- level-to-motor mapping;
- config validation.

Requirements:
- pure DSP functions/classes can be unit tested with generated arrays;
- Windows WASAPI capture is an adapter;
- motor output is an adapter/port;
- changing output audio device can restart capture without restarting the full service;
- disabling haptics always drives motors to neutral;
- invalid numeric config is rejected or normalized safely.

Do not redesign the haptic algorithm for subjective quality in P0 unless a bug is proven. P0 protects behavior and architecture; tuning belongs later.

## Workstream E — Touchpad engine extraction

Separate gesture interpretation from Windows `SendInput`.

Requirements:
- gesture interpreter accepts controller touch samples/events and returns semantic actions;
- Windows mouse output executes semantic actions;
- one-finger pointer, tap, two-finger scroll/tap and current L3/R3 behavior remain supported;
- disable/disconnect/shutdown releases synthesized button state;
- gesture state reset is deterministic;
- unit tests cover tap vs movement, one/two finger transitions and release behavior.

## Workstream F — Configuration and profiles

Create a repository/service boundary for config and profiles.

Requirements:
- typed/default schema;
- schema/config version;
- atomic save where practical;
- safe fallback for malformed config;
- built-in profiles cannot become silently corrupted;
- user profiles are separated from bundled defaults;
- API returns validation errors instead of generic 500s.

Preserve existing user-facing baseline values unless there is a migration rule.

## Workstream G — Logging, errors and health

Add structured logging suitable for troubleshooting controller/hardware issues.

At minimum include events for:
- service startup/shutdown;
- controller connect/disconnect/reconnect;
- audio device open/change/error;
- profile/config load/save/validation failure;
- WebSocket connect/disconnect;
- unexpected worker failure.

Requirements:
- no blanket `except Exception: pass` on operational paths;
- stable error codes/tags for major failure families;
- user-safe message separated from debug detail when appropriate;
- health snapshot available to API.

## Workstream H — Local HTTP API

Add a small versioned API, preferably `/api/v1`.

Minimum endpoints/contracts:
- `GET /api/v1/health`;
- `GET /api/v1/state`;
- `GET /api/v1/profiles`;
- `GET /api/v1/config`;
- `PUT/PATCH /api/v1/config`;
- command to enable/disable haptics;
- command to enable/disable touchpad;
- profile load/save commands as needed.

Requirements:
- bind to loopback by default;
- explicit CORS/origin policy;
- typed request/response models;
- hardware object never serialized;
- API process lifecycle coordinated with core lifecycle.

## Workstream I — WebSocket realtime

Add a versioned realtime channel.

Minimum event categories:
- connection state changed;
- state snapshot/update;
- audio device/status changed;
- profile/config changed;
- recoverable error/diagnostic event.

Requirements:
- client receives an initial snapshot after connect;
- reconnecting clients can recover without restarting core;
- events have type + version + payload contract;
- backpressure/noisy telemetry is bounded;
- do not stream raw controller input continuously in P0 unless required for a test/diagnostic path.

## Workstream J — Legacy GUI compatibility

P0 may keep the legacy `customtkinter` GUI as a temporary local client or maintenance surface, but it must no longer own core hardware state.

Acceptable outcomes:
- GUI consumes the new application services directly behind stable interfaces; or
- GUI becomes a client of the local API.

Do not spend P0 polishing the legacy UI. P1 replaces the primary presentation layer.

## Workstream K — Automated tests

Add a meaningful test suite.

Minimum coverage areas:
- DSP mapping/gates/transients;
- config validation/migration/fallback;
- controller lifecycle state machine with fake adapter;
- reconnect and shutdown behavior;
- gesture interpretation;
- synthesized mouse button release on reset/teardown;
- API health/state/config happy paths and validation failures;
- WebSocket initial snapshot and state-change event;
- no hardware required for normal unit/integration test suite.

Hardware tests should be separately marked/manual.

## Workstream L — Tooling / CI

Add reproducible developer commands for:
- install/setup;
- format;
- lint;
- tests;
- run core;
- run legacy UI if retained;
- build baseline executable/package if still supported in P0.

CI should at least run static/lint/test checks on pushes/PRs. Windows CI is preferred for Windows-specific import/build validation where feasible.

## Security/local exposure requirements

- loopback bind by default;
- no `0.0.0.0` default;
- no Cloudflare Tunnel auto-start;
- no unauthenticated internet exposure;
- validate API input before touching hardware;
- do not execute shell/process commands from API input.

## Deliverables

P0 implementation must leave:
- refactored source tree;
- preserved upstream attribution/provenance;
- API + WebSocket contracts;
- test suite;
- CI workflow(s);
- updated README developer setup;
- `docs/ARCHITECTURE.md`;
- `docs/API.md` or generated equivalent;
- updated D0/P0 smoke documentation;
- concise migration note from upstream structure to P0 structure.

## Verification gate

Before declaring P0 complete, run and report:

1. formatter/lint;
2. static/type checks configured by the project;
3. complete automated test suite;
4. build/package checks available without hardware;
5. API smoke test;
6. WebSocket smoke test;
7. Windows USB hardware checklist from `docs/D0_SMOKE_CHECKLIST.md` when hardware is available;
8. search/audit confirming no new Bluetooth/wireless implementation entered P0.

## Definition of GO

P0 is GO only if:
- architecture boundaries are materially improved, not just files renamed;
- haptics and touch behavior remain functional on USB;
- controller lifecycle is deterministic and observable;
- core runs without the legacy GUI;
- API and WebSocket expose stable state/contracts;
- tests cover the extracted logic;
- there are no critical swallowed exceptions in operational paths;
- wired-only constraint was respected;
- no known blocker is hidden behind TODOs.

A technical GO for P0 is not approval for P1/P2 features, release, merge to production distribution or wireless work.
