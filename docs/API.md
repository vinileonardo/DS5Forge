# DS5Forge local API v1

The optional local server is started by the legacy desktop runtime on
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

Expected failures use an error object with `code`, safe `message`, optional
`detail`, `recoverable` and `fields`. Request bodies use strict Pydantic
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
origin was explicitly allowed when constructing the local app.
