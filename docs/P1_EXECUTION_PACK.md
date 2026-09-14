# DS5Forge — P1 Execution Pack

## Sprint

P1 — PC-first UX / Web + Desktop

## Goal

Replace the legacy `customtkinter` GUI as the primary DS5Forge presentation with a modern PC-first TypeScript frontend that consumes the P0 local HTTP/WebSocket contracts, runs in a normal browser and inside a thin Tauri 2 desktop shell, and accurately represents connected/offline/degraded controller states.

P1 is a presentation/client sprint. The P0 Python core remains the hardware authority. Do not move controller, WASAPI, touchpad or Windows HID behavior into the frontend or the desktop shell.

## Starting point

P1 starts from the P0 technical-GO commit and must preserve the P0 architecture and automated gates.

Important P0 status that remains true at P1 start:

- Python 3.12.x is the supported core runtime;
- HTTP API is versioned under `/api/v1`;
- realtime endpoint is `/api/v1/ws`;
- API binds to loopback only;
- controller hardware ownership stays in the Python core;
- P0 automated review is GO;
- physical Windows + real DualSense USB smoke validation is still a separate pending gate and must not be rewritten as PASS without evidence.

## Mandatory reading before implementation

1. `AGENTS.md`
2. `docs/D0_BASELINE_AND_ROADMAP.md`
3. `docs/P0_EXECUTION_PACK.md`
4. `docs/P0_VALIDATION.md`
5. `docs/ARCHITECTURE.md`
6. `docs/API.md`
7. `docs/P1_UX_SPEC.md`
8. relevant P0 source/contracts before changing any API behavior

If this Execution Pack conflicts with the D0 roadmap or AGENTS instructions, stop and surface the conflict instead of guessing.

## Hard exclusions

Do not implement in P1:

- Bluetooth, wireless transports or pairing;
- wireless audio/haptics tuning;
- raw controller input monitor (P2);
- lightbar editor (P2);
- adaptive trigger lab/presets (P2);
- stick calibration/deadzone lab (P2);
- game/process detection (P3);
- auto-profile by game (P3);
- remapping/chords beyond current upstream behavior (P3);
- XInput/virtual controller/HidHide (P3);
- Cloudflare remote exposure (P4);
- public/network bind of the core (P4);
- installer, updater, auto-start, tray or release productization (P4);
- bundling the Python core as a Tauri sidecar in a release artifact (P4);
- rewriting the Python core in Rust/C++;
- replacing working P0 services merely because the frontend stack is new.

## Locked implementation direction

### Frontend

Use a modern SPA under `frontend/`:

- React;
- TypeScript with strict checks;
- Vite;
- React Router for page routing;
- TanStack Query (or a comparably small server-state layer) for HTTP query/mutation state;
- Zod or equivalent runtime validation for external API/WebSocket payload boundaries;
- Tailwind CSS plus accessible headless primitives (Radix UI or equivalent) for the design system;
- Lucide or equivalent lightweight icon set;
- no server-side rendering framework is needed.

Prefer a small dependency surface. Do not add a general global-state framework unless the implementation demonstrates a real need beyond query/realtime state.

### Desktop shell

Use Tauri 2 under the same `frontend/` project (for example `frontend/src-tauri/`).

P1 shell requirements:

- show the exact same SPA used in the browser;
- target Windows first;
- no duplicate UI implementation;
- no arbitrary shell/process execution permission;
- do not bundle or release the Python core as a sidecar yet;
- during P1 development, the Python core may be started separately with `python source/run.py --headless`;
- a missing core must be shown as an explicit offline state, never as a blank/broken window.

P4 owns definitive installer/sidecar/update/tray/autostart productization.

## Core/API contract authority

The frontend must consume the P0 contracts instead of inventing parallel state.

Existing P0 HTTP surface:

- `GET /api/v1/health`
- `GET /api/v1/state`
- `GET /api/v1/config`
- `PUT/PATCH /api/v1/config`
- `GET /api/v1/profiles`
- `POST /api/v1/profiles/{name}/load`
- `PUT /api/v1/profiles/{name}`
- `DELETE /api/v1/profiles/{name}`
- `POST /api/v1/commands/rumble`
- `POST /api/v1/commands/touchpad`
- `POST /api/v1/commands/rumble/test`

Existing P0 WebSocket:

- `/api/v1/ws`
- first frame: `state.snapshot`
- event families: `controller.lifecycle`, `state.updated`, `audio.status`, `config.changed`, `profile.changed`, `diagnostic`

Any P1 backend contract change must be minimal, documented in `docs/API.md`, backward-compatible where practical and covered by Python tests.

## Required P1 backend adjustment: local frontend origins

P0 intentionally shipped with CORS/origin support opt-in. P1 introduces a real browser/Tauri client, so the core must gain a narrow local-origin policy suitable for the P1 frontend.

Requirements:

- never use wildcard CORS;
- never change the HTTP bind from loopback-only;
- allow only explicitly validated local development/browser origins and the local Tauri origin required on Windows;
- expected local origins include Vite loopback development/preview origins and `http://tauri.localhost` when applicable;
- origin configuration must be testable;
- WebSocket and HTTP origin policy must remain consistent;
- no internet hostname may be silently accepted;
- remote/Cloudflare origin support remains P4 and requires an explicit security design before enablement.

## Frontend architecture

Suggested structure (names may vary while preserving boundaries):

```text
frontend/
  src/
    app/
      router.tsx
      providers.tsx
    components/
      layout/
      status/
      forms/
      feedback/
    features/
      overview/
      haptics/
      touchpad/
      profiles/
      diagnostics/
      settings/
    lib/
      api/
        client.ts
        contracts.ts
        errors.ts
      realtime/
        socket.ts
        reducer.ts
      formatting/
    styles/
    main.tsx
  tests/
  e2e/
  src-tauri/
  package.json
  package-lock.json
  vite.config.ts
  tsconfig*.json
```

Rules:

1. API/WebSocket code stays outside page components.
2. Page components never know about Python hardware objects.
3. HTTP responses and WebSocket frames are runtime-validated at the boundary.
4. Realtime updates converge into one coherent runtime view instead of duplicating independent state copies.
5. Mutations have optimistic UI only when failure rollback is deterministic; otherwise show pending state and apply server truth.
6. Server errors use the P0 structured error contract and remain visible/actionable.
7. No page may infer `connected` from stale data after API/WebSocket loss.

## Workstream A — Frontend foundation

Create the `frontend/` workspace with reproducible npm commands for:

- install;
- dev;
- lint;
- format/check;
- typecheck;
- unit/component tests;
- production web build;
- e2e smoke where practical;
- Tauri development/build validation.

Requirements:

- commit lockfile;
- strict TypeScript;
- no secrets in frontend env files;
- API base URL defaults to the P0 loopback endpoint and is configurable only through an explicit local-development mechanism;
- no hard dependency on a cloud service.

## Workstream B — Application shell / navigation

Create a PC-first app shell:

- persistent left navigation on desktop;
- compact/mobile navigation below the desktop breakpoint;
- top/global controller connection status;
- clear product identity (`DS5Forge`);
- main content area with stable width and hierarchy;
- global offline/reconnecting/degraded banner or status surface;
- accessible keyboard focus states.

Primary routes:

- `/` or `/overview` — Overview
- `/haptics`
- `/touchpad`
- `/profiles`
- `/diagnostics`
- `/settings`

No P2/P3 placeholder pages are required. Avoid dead navigation items.

## Workstream C — HTTP bootstrap and realtime state

On startup:

1. fetch health/state/config/profiles as needed;
2. open `/api/v1/ws`;
3. accept the initial `state.snapshot` as authoritative realtime state;
4. merge subsequent version-1 events safely;
5. reconnect automatically with bounded backoff and jitter;
6. after a WebSocket reconnect, refresh authoritative HTTP data that can have changed while offline;
7. expose explicit `online`, `reconnecting`, `offline` and `protocol/error` client states.

Requirements:

- no infinite tight reconnect loop;
- no full page reload required after backend reconnect;
- stale controller state must be visually marked or invalidated when the core becomes unreachable;
- malformed/unknown event payloads must not crash the app;
- unknown future event types may be ignored/logged safely while known contract version mismatches surface a diagnostic client error.

## Workstream D — Overview

Build the main controller overview using current P0 data only.

Show where available:

- connection state;
- controller model/identity;
- USB transport indication;
- battery level and charging state;
- active profile;
- haptics enabled/disabled;
- touchpad enabled/disabled;
- audio capture state/device;
- capabilities summary;
- health/degraded summary;
- last recoverable/unrecoverable error when present.

Actions:

- enable/disable haptics;
- enable/disable touchpad;
- navigate to detailed panels.

Do not fabricate lightbar/adaptive-trigger controls merely because capabilities fields exist. Those belong to P2.

## Workstream E — Haptics panel

Build a usable P1 editor for the existing P0 rumble configuration.

Requirements:

- expose current validated fields from `config.rumble` with human-readable labels/help;
- use numeric controls with safe min/max/step based on the core validation contract;
- group advanced DSP values so the normal experience is understandable;
- allow save/apply via the existing config endpoint;
- surface field-level 422 errors from the core;
- support enable/disable rumble;
- support the bounded rumble test command;
- test/preview action must clearly stop/finish and never look permanently active;
- no new subjective DSP algorithm redesign in P1.

## Workstream F — Touchpad panel

Expose the current P0 touchpad configuration:

- enabled-on-start;
- pointer speed;
- acceleration;
- acceleration cap;
- scroll speed;
- tap-to-click;
- live enable/disable command.

Requirements:

- clear explanation that this controls mouse/gesture behavior;
- field validation aligned with the Python core;
- no gesture editor or raw touch visualization yet (P2);
- disabled/offline hardware states must disable unsafe actions while still allowing valid persisted configuration edits where the backend permits them.

## Workstream G — Profiles

Create complete profile management for the existing P0 API:

- list bundled and user profiles;
- visually distinguish bundled/read-only vs user/editable;
- load/apply a profile;
- save current haptics settings into a user profile;
- delete only editable user profiles;
- confirm destructive delete;
- prevent UI attempts to overwrite bundled profile names;
- surface server validation/not-found errors;
- update active profile after realtime/HTTP confirmation.

Avoid adding game association/auto-profile behavior; that is P3.

## Workstream H — Diagnostics

Build a useful diagnostic view from current P0 state/health/events.

Show:

- core reachable/unreachable;
- controller lifecycle state;
- subsystem health map;
- degraded reasons;
- audio status/device/error;
- last structured runtime error with code/message/recoverability;
- sequence/update timestamp where useful;
- frontend connection/reconnect state;
- client protocol/runtime validation errors.

P1 may keep a small bounded in-memory event timeline for the current UI session if it is sourced from existing WebSocket events and does not become a new backend logging subsystem.

Do not implement log export or guided support bundles yet; those belong to P4.

## Workstream I — Settings

Settings should contain only currently supported product/client settings.

At minimum:

- theme selection mapped to the existing config contract (`Light`, `Dark`, `Liquid Glass`) or an explicitly documented migration that remains backward compatible;
- microphone button behavior mapped to `master`, `rumble`, `trackpad`;
- display the local API endpoint as informational/read-only unless a safe local-only configuration mechanism is explicitly added.

For new/default P1 presentation, the product visual language is dark-premium. Existing persisted user theme must not be silently discarded.

## Workstream J — Design system and accessibility

Follow `docs/P1_UX_SPEC.md`.

Requirements:

- dark premium PC application feel, not a generic admin dashboard;
- restrained motion;
- clear connected/degraded/error semantics;
- readable density on 1366x768 and larger desktop displays;
- responsive usable layout at mobile widths;
- keyboard navigation for primary controls;
- semantic labels for toggles/forms;
- visible focus states;
- adequate contrast;
- no color-only status communication;
- honor `prefers-reduced-motion`.

## Workstream K — Desktop shell

Add Tauri 2 around the same frontend.

P1 acceptance:

- `tauri dev` opens DS5Forge and renders the same SPA;
- the shell communicates only with the local loopback Python API/WebSocket;
- window minimum size prevents unusable layout;
- app title/icon metadata are reasonable;
- a core-offline launch renders a proper reconnect/offline UX;
- no installer/release updater/tray/autostart work;
- no broad Tauri shell permissions;
- CSP/connect-src permits only what the local DS5Forge client actually needs.

## Workstream L — Legacy GUI transition

P1 must make the web/Tauri UI the primary documented presentation path.

Requirements:

- legacy `customtkinter` code may remain temporarily as a fallback/reference;
- do not delete it until parity is demonstrated and tests/smoke checklist cover the replacement;
- README/developer docs must prefer headless core + frontend/Tauri for P1 usage;
- legacy GUI must not regain hardware ownership or become a second source of truth;
- if a known legacy-only behavior cannot be reached from the new UI, document it as a P1 blocker rather than silently removing it.

## Workstream M — Tests

Frontend minimum automated coverage:

- API client success + structured-error handling;
- runtime schema validation;
- WebSocket initial snapshot;
- state updates;
- reconnect/backoff behavior with fake timers where appropriate;
- offline/stale-state behavior;
- Overview disconnected/connected/degraded rendering;
- haptics config mutation and validation errors;
- touchpad config mutation and validation errors;
- profile bundled/editable behavior;
- diagnostics error rendering;
- primary navigation and responsive shell behavior;
- no hardware required for normal frontend tests.

Integration/E2E:

- run against a deterministic fake/mock API or a real P0 core composed with fake adapters;
- cover browser bootstrap -> WS snapshot -> mutation -> reflected realtime state;
- cover backend temporarily unavailable -> reconnect without manual page reload.

Keep all existing Python tests passing.

## Workstream N — CI

Extend GitHub Actions so P1 cannot merge with a broken frontend.

At minimum add frontend gates for:

- npm clean install from lockfile;
- formatting/lint;
- TypeScript check;
- unit/component tests;
- production Vite build;
- E2E smoke if stable in CI;
- Tauri compile/build validation on Windows where practical without turning P1 into installer productization.

Keep all P0 Python/Linux and Windows package/import gates.

Do not weaken existing gates to make P1 green.

## Documentation deliverables

Update/create:

- `README.md` — P1 primary run path;
- `docs/DEVELOPMENT.md` — Python + Node/Rust/Tauri prerequisites and commands;
- `docs/API.md` — only if P1 changes origin/config behavior or contracts;
- `docs/ARCHITECTURE.md` — add frontend + Tauri client topology;
- `docs/D0_SMOKE_CHECKLIST.md` — add new UI/browser/Tauri manual checks without rewriting pending hardware evidence;
- `docs/P1_VALIDATION.md` — actual results, commands, known limitations and hardware status at the end of implementation/review.

## Required developer commands

The exact scripts may vary, but a clean contributor must have obvious commands equivalent to:

```text
# core
python source/run.py --headless

# web UI
cd frontend
npm ci
npm run dev
npm run lint
npm run typecheck
npm test
npm run build

# desktop shell
npm run tauri dev
```

Document any Windows prerequisites required by Tauri; do not auto-install system toolchains from project scripts.

## Security requirements

- Python API stays loopback-only;
- no wildcard CORS;
- no automatic Cloudflare Tunnel;
- no remote origins in P1 defaults;
- Tauri CSP is explicit and narrow;
- frontend never accepts arbitrary API URLs from query parameters;
- no arbitrary command execution from Tauri;
- no secrets/tokens embedded in frontend;
- validate all external HTTP/WebSocket payloads before use;
- destructive profile actions require confirmation;
- controller output remains validated by the Python core even if frontend validation exists.

## Performance expectations

P1 is not a benchmark sprint, but the UI must remain responsive under normal WebSocket state traffic.

- avoid rerendering the entire app on every event;
- do not store unbounded event history;
- do not poll high-frequency endpoints while WebSocket is healthy;
- do not add raw 250 Hz input streaming;
- initial useful UI should render promptly once the local core responds.

## Verification gate

Before declaring P1 implementation complete, run and report:

1. existing P0 Python formatter/lint/type/test gates;
2. Python package/build checks still relevant to P0;
3. frontend format/lint;
4. frontend strict typecheck;
5. frontend unit/component tests;
6. frontend production build;
7. browser integration/E2E smoke;
8. WebSocket reconnect/offline smoke;
9. Windows Tauri compile/dev/build validation as available;
10. local-origin security tests (HTTP + WebSocket);
11. audit confirming no Bluetooth/wireless/P2/P3/P4 scope entered accidentally;
12. updated manual Windows + wired DualSense smoke checklist when hardware is available.

## Definition of GO

P1 is technically GO only if:

- the primary user flow works through the new frontend without relying on legacy `customtkinter`;
- browser and Tauri use the same frontend codebase;
- all displayed controller state is sourced from P0 HTTP/WebSocket contracts;
- backend loss is represented as offline/reconnecting, never as stale success;
- backend reconnect recovers without manual reload;
- Haptics, Touchpad, Profiles, Settings and Diagnostics are operational against the current core surface;
- local CORS/WebSocket origin handling is narrow and tested;
- existing P0 automated gates remain green;
- frontend automated gates are green;
- wired-only scope remains intact;
- no installer/release/Cloudflare/P2/P3 functionality was pulled forward;
- known hardware-validation status is reported truthfully.

A P1 technical GO is not approval for P2 hardware-lab features, P3 compatibility/game automation, P4 release/productization, wireless work, merge or public distribution.
