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
| GET/PUT | `/controller/sticks/calibration` | Read/apply center offsets and radial deadzones used by DS5Forge Exclusive virtual mirroring |
| POST | `/controller/sticks/calibration/estimate` | Analyze 12–512 stationary stick samples and return center drift, residual jitter and a bounded deadzone recommendation |
| GET/PATCH | `/controller/gestures` | Read/update validated touch gesture settings |
| GET/POST | `/games` | List or add strict executable-based game rules |
| GET/PUT/DELETE | `/games/{id}` | Read, replace or remove one game rule |
| GET | `/games/active` | Active game and automation projection |
| POST | `/games/{id}/test-match` | Evaluate one rule against the current foreground observation |
| GET | `/foreground` | Current PID, executable, optional path, title and diagnostic |
| GET/PUT | `/automation` | Read or update enabled state, exit policy and default profile |
| GET/PUT | `/compatibility` | Read or request Native, Remap or Virtual/XInput mode |
| GET/PUT | `/mappings` | Read or atomically replace validated remappings |
| GET/PUT | `/chords` | Read or atomically replace validated input chords |
| GET | `/diagnostics/conflicts` | Best-effort process-name conflict diagnostics |
| GET | `/diagnostics/duplicate-input` | Physical/virtual visibility and duplicate-input risk |
| GET | `/games/candidates` | Running/recent executable candidates; never persists a game |
| GET | `/exclusive/capabilities` | Provider, output-report and suppression capability gates |
| GET | `/exclusive/status` | Current Exclusive mode, ownership generation and watchdog state |
| POST | `/exclusive/enable` | Start a verified Exclusive transaction or return structured unavailable/rollback error |
| POST | `/exclusive/disable` | Unsuppress physical input and close the virtual session |
| POST | `/exclusive/heartbeat` | Refresh the active ownership/watchdog lease |
| GET/PUT/POST | `/controller/player-leds`, `/controller/player-leds/reset` | Separate Player LED state and intensity |

Controller Lab writes are strict and capability-gated. Unsupported lightbar,
trigger or rumble operations return a structured error and do not call the
adapter. Trigger previews have a server-side 10–5000 ms TTL and reset both
triggers to Off on timeout/cancel/disconnect/reconnect/shutdown. Haptics tests
are also bounded and neutralized before audio-driven rumble resumes. Stick calibration never rewrites native physical HID input: center correction and radial deadzone are currently applied to DS5Forge-controlled Exclusive virtual mirroring. The estimate endpoint is advisory until its returned calibration is explicitly applied.

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
P3 additionally emits `game.foreground_changed`, `game.detected`,
`game.activated`, `game.deactivated`, `game.rule_applied`,
`compatibility.changed`, `game.conflict_detected`, `automation.changed` and
`synthetic.release`. Events are version 1; clients ignore unknown future event
types safely.
P5 additionally emits `exclusive.changed`, `exclusive.recovered`,
`diagnostics.duplicate_input` and `adaptive_trigger.changed`. `controller.lab`
also carries Player LED and lightbar effect state. Exclusive ownership tokens
are never serialized to clients.
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

## P3 game/automation behavior

The registry is persisted as a separate schema-v2 `games.json` and migrates the
unreleased P3 schema-v1 single-executable shape on load. Each game may declare
one or more executable names; matching is case-insensitive and may additionally
require an exact case-insensitive executable path when exactly one executable is
configured. Window titles are never identity. A rule
evaluation includes every rule's matched/not-matched result, reason and
action. Automation stores the previous profile/mode before automatic apply,
releases synthetic outputs across game/profile/mode transitions and uses
`restore_previous` by default on exit. Manual changes mark an active context as
an override until a real foreground transition.

`native` is the safe default. `remap` enables validated keyboard/mouse outputs
without XInput. Keyboard codes are limited to the installed SendInput adapter
and support bounded `+` combinations such as `CTRL+SHIFT+S`; overlapping
combinations reference-count shared physical keys. Mouse mappings support
left/right/middle plus Mouse4/Mouse5. Logical output is
reserved until an explicit production adapter exists and is rejected by the
registry today. `virtual` is only operational when an injected
provider reports installation, availability and reliable physical suppression;
otherwise the request returns structured `compatibility.unavailable` and the
previous mode remains unchanged. Conflict diagnostics are process-name
evidence only. Steam process presence is informational and does not imply
Steam Input is active; it may already be disabled for the current game. No
external process is controlled.

Exclusive is a separate capability-gated mode. It requires a verified virtual
output-report source and session-scoped physical suppression; provider presence
alone is insufficient. It is OFF by default and duplicate-input risk remains
true whenever suppression is not verified. Native, remapping and Exclusive
state are never inferred from stale WebSocket data.

## P4 product contracts

The following remain under `/api/v1` and use strict request/response models:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/app/info` | Canonical version, API version, wired scope and feature flags |
| GET/POST | `/lifecycle`, `/lifecycle/restart`, `/lifecycle/stop` | Product lifecycle and bounded manual core/release control |
| GET/POST | `/diagnostics/guided`, `/diagnostics/support-bundle` | Guided statuses and sanitized bounded ZIP |
| POST | `/updates/check` | Validate signed HTTPS metadata and reject downgrades |
| GET | `/remote/status` | Remote OFF/session/origin state |
| POST | `/remote/pairing/start` | Local one-use pairing challenge |
| POST | `/remote/pairing/complete` | Exact HTTPS-origin completion and HttpOnly cookie |
| POST | `/remote/disable` | Revoke/close sessions and stop tunnel |
| POST | `/remote/sessions/{id}/revoke` | Revoke one session |
| GET/PUT/POST | `/tunnel/status`, `/tunnel/configure`, `/tunnel/start`, `/tunnel/stop` | Explicit cloudflared detection/configuration/control |

Remote-origin HTTP and WebSocket requests are admitted only when their exact
HTTPS Origin is registered and the `ds5forge_session` cookie authenticates the
same session. Cookies are not accepted from query strings. Local origin-less
clients retain the existing loopback behavior; an origin-less request whose
`Host` matches a registered remote origin is still treated as remote and
requires the same cookie. Unapproved browser origins are rejected before
commands reach the facade.

JSON request bodies are bounded at 256 KiB before handler dispatch; update,
pairing and tunnel fields have smaller schema limits. Oversized bodies return
structured `413 api.payload_too_large`.
