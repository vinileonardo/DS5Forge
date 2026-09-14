# DS5Forge local API v1

The optional local server is started by the desktop runtime on
`127.0.0.1:8765` by default. P0 enforces loopback-only binding (`127.0.0.1`,
`::1` or `localhost`) and rejects external bind addresses. It is not an internet-facing API. The headless
entry point can run the same core without the GUI:

```text
python source/run.py --headless
```

## HTTP endpoints

All paths use `/api/v1`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Process health, controller availability and degraded subsystems |
| GET | `/state` | Immutable runtime snapshot; no hardware object is serialized |
| GET | `/config` | Validated schema-v1 config |
| PUT/PATCH | `/config` | Replace or merge config; invalid values return a structured 422 |
| GET | `/profiles` | Bundled/user profile index |
| POST | `/profiles/{name}/load` | Validate and apply a profile |
| GET | `/profiles/{name}` or `/profiles/{name}/export` | Export a schema-v2 full controller profile |
| PUT/DELETE | `/profiles/{name}` | Save/delete a user profile; full saves require `confirm_overwrite` when replacing |
| POST | `/profiles/import` | Validate and save JSON text for a schema-v2 profile |
| POST | `/commands/rumble` | Body: `{"enabled": true}` |
| POST | `/commands/touchpad` | Body: `{"enabled": true}` |
| POST | `/commands/rumble/test` | Optional bounded `left`, `right`, `duration_ms` |
| GET | `/controller/input` or `/controller/telemetry` | Current normalized input projection with sequence/timestamp |
| GET/PUT/POST | `/controller/lightbar`, `/controller/lightbar/reset` | Read, apply or reset capability-gated lightbar state |
| GET/PUT/POST/DELETE | `/controller/triggers`, `/controller/triggers/{left\|right}`, `/controller/triggers/preview`, `/controller/triggers/reset` | Configure, preview, cancel or reset adaptive triggers |
| POST/DELETE | `/controller/haptics/test` | Start/cancel a bounded, single-flight haptics test |
| GET/PUT | `/controller/sticks/calibration` | Save DS5Forge-only stick visualization metadata |
| GET/PATCH | `/controller/gestures` | Read/update validated touch gesture settings |

Controller Lab writes are strict and capability-gated. Unsupported lightbar,
trigger or rumble operations return a structured error and do not call the
adapter. Trigger previews have a server-side 10–5000 ms TTL and reset both
triggers to Off on timeout/cancel/disconnect/reconnect/shutdown. Haptics tests
are also bounded and neutralized before audio-driven rumble resumes.

Profile documents use schema version 2 and contain `rumble`, `lightbar`,
`triggers`, `sticks` and `touchpad` sections. Legacy rumble-only bundled/user
profiles are migrated in memory without losing rumble values. Imports are JSON
text only, limited to 64 KiB, reject non-finite numbers/unknown fields and do
not modify the existing profile until every section validates. Bundled names
are case-insensitively reserved and all user writes are atomic.

Expected failures, including FastAPI request validation failures, use an error
object with `code`, safe `message`, optional `detail`, `recoverable` and
`fields`. Request bodies use strict Pydantic
contracts: unknown fields, numeric/boolean coercion and explicit `null` values
for patch fields are rejected with 422 before controller output is attempted.

## WebSocket

Connect to `/api/v1/ws`. The first frame is always:

```json
{"type":"state.snapshot","version":1,"payload":{"state":{}}}
```

Subsequent frames use the same `{type, version, payload}` envelope. P2 emits:
`controller.lifecycle`, `controller.input`, `controller.lab`, `state.updated`,
`audio.status`, `config.changed`, `profile.changed` and `diagnostic`.
`controller.input` is latest-value telemetry published at no more than about
30 Hz, even though the core continues its approximately 250 Hz USB read loop
for touchpad behavior. Subscription queues are bounded and retain the newest
event when a client is slow; no telemetry history is retained.
Browser WebSocket connections with an `Origin` header are rejected unless that
origin was explicitly allowed when constructing the local app. HTTP requests
that carry an unapproved browser `Origin` are also rejected with structured
`403 api.origin_rejected`; CORS headers are not treated as CSRF protection. The
P1 default allow-list is deliberately narrow and shared by HTTP enforcement,
HTTP CORS and WebSocket validation:

- `http://localhost:5173` and `http://127.0.0.1:5173` for Vite development;
- `http://localhost:4173` and `http://127.0.0.1:4173` for Vite preview;
- `http://tauri.localhost` for the Tauri 2 desktop shell.

Wildcard, HTTPS/internet, alternate ports, paths and query-bearing origins are
rejected. Requests without an `Origin` header remain usable for local native
clients; this does not broaden browser CORS access.
