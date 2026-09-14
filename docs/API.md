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
| PUT/DELETE | `/profiles/{name}` | Save/delete a user profile |
| POST | `/commands/rumble` | Body: `{"enabled": true}` |
| POST | `/commands/touchpad` | Body: `{"enabled": true}` |
| POST | `/commands/rumble/test` | Optional bounded `left`, `right`, `duration_ms` |

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

Subsequent frames use the same `{type, version, payload}` envelope. P0 emits:
`controller.lifecycle`, `state.updated`, `audio.status`, `config.changed`,
`profile.changed` and `diagnostic`. Subscription queues are bounded and retain
the newest event when a client is slow. Raw controller input is not streamed.
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
