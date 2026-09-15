# DS5Forge — P3 Execution Pack

## Sprint

P3 — Compatibility / Games / Automation

## Baseline and handoff

This sprint is based on commit `a9df75c0018230b219e323c6ca159f286a6093d3`
and is isolated on `feat/p3-compat-games-automation`. The P2 branch is not
modified. Existing untracked review artifacts are preserved. P3 is delivered
for independent review; it does not commit, push, merge or deploy.

## Binding scope

- P0–P4 remain USB/wired only. There is no Bluetooth, wireless transport,
  pairing, dongle or wireless tuning work in P3.
- The Python core remains the only authority for controller state, foreground
  observations, profiles and synthetic output ownership.
- Browser/UI code consumes immutable snapshots and `/api/v1` HTTP/WebSocket
  contracts. It does not import `pydualsense`, WASAPI or Windows HID APIs.
- Win32 foreground/process inspection and `SendInput` adapters live only under
  `source/dualsense_companion/platform/windows/`.
- Native is the initial and default compatibility mode. Remap is explicit and
  does not require XInput. Virtual/XInput is modeled and capability-gated, but
  no production provider, driver, HidHide/ViGEm service or installer is added.
- Tauri remains the existing thin shell. P3 adds no native permission,
  sidecar, process-control, installer, updater, tray or autostart capability.

## Workstreams

### A — Domain and persistence

`domain.games` contains frozen contracts for foreground observations, game
definitions/matches, rule explanations, automation state, compatibility state,
mappings, chords, synthetic ownership, release reports, conflict diagnostics
and virtual-controller capability. `games.json` is separate from the P2
`config.json` and uses schema v2 for one-or-more executable identities per game,
with migration from the unreleased P3 schema-v1 single-executable shape. It also
contains automation policy, mappings, chords, compatibility preference and
process names for best-effort conflict diagnostics.

The registry rejects unknown fields, duplicate IDs, invalid executable sets/path
forms, malformed profile references, unsupported inputs/outputs, duplicate
mapping sources, ambiguous/overlapping subset chord signatures and invalid
enum/range values.
Validation completes before the in-memory document or remapper is replaced.
Writes use the existing fsync-and-replace atomic writer. Invalid saved data is
replaced in memory by a safe default document and exposed as a structured,
recoverable diagnostic.

### B — Foreground and automation

The platform-neutral `ForegroundDetector` port produces PID, executable name,
optional full path, title, liveness and observation time. The Windows adapter
uses Win32/ctypes; the worker polls every 500–1000 ms with an interruptible
shutdown. Inspection failures become desktop/unavailable observations and do
not terminate the worker.

Rules match any configured executable name case-insensitively and optionally
require an exact case-insensitive path for a single-executable rule. Window
titles are diagnostic only. Each observation
publishes the evaluated rules and an explanation. Real context transitions
support game A → game B, game → desktop, process/window exit and recovery.
`restore_previous` is the default exit policy; `apply_default` and
`keep_current` are explicit alternatives. A failed game A → game B transition
runs the configured exit recovery instead of leaving game A state orphaned.
Foreground transitions and compatibility/remap changes are serialized so the
polling worker and HTTP commands cannot interleave a partial transition. A
manual profile/mode change marks the active context as a manual override and
prevents reapplication until a real context transition.

### C — Remapping and safety

The shared `OutputManager` owns keyboard/mouse outputs and retains a gated
logical/virtual boundary for a future explicit adapter. Persisted P3 mappings
reject logical outputs while no production adapter exists, instead of allowing
a configuration that would fail only at runtime. Keyboard targets support
bounded `+` combinations such as `CTRL+SHIFT+S`; the Windows adapter reference-
counts shared physical keys so overlapping combinations cannot release each
other's modifiers. Mouse-button ownership is also reference-counted across the
legacy touchpad/L3/R3 path and P3 remapping so one synthetic source cannot
release another source's held button. `RemappingEngine` is edge-driven,
debounced and deterministic: chord candidates hold simple mappings through the
longest still-valid bounded window, a completed chord wins, and a quick tap
falls back to a complete simple press/release cycle. Ambiguous subset chords in
overlapping scopes are rejected at persistence time instead of allowing both
outputs to fire. Game-scoped rules are active only in their matching game
context; global rules remain available in remap mode.

Every disconnect, reconnect, shutdown, profile/mode/game transition,
deactivation, automation disable, remapper exception and rollback invokes the
release path. Cleanup is best-effort across all adapters and returns a typed
release report even if one adapter fails.

### D — Compatibility and conflicts

`native`, `remap` and `virtual` are explicit API/UI states. Virtual activation
requires an injected provider that reports installation, availability and
reliable physical suppression. Without that capability the request fails with
`compatibility.unavailable` and the previous mode remains authoritative.
Physical input visibility, virtual input activity, suppression and
double-input risk are always published. Remap explicitly reports double-input
risk because the physical DualSense remains visible while keyboard/mouse
synthetic output can also be consumed by the foreground game or Steam Input.

The provider investigation ends at this provider-neutral boundary in P3. No
Windows virtual-gamepad driver/service was selected or installed because safe
operation also requires reliable physical suppression and an explicit double-
input decision. A future provider must be approved and validated separately;
the injectable fake is test infrastructure only, and provider selection is
deferred to a dedicated P4 decision.

Conflict diagnostics inspect process names only. Steam is reported as a
possible conflict with the exact caveat that Steam Input may affect a game
depending on its configuration. DS5Forge never claims Steam Input is active,
never kills a process and never changes external software settings.

### E — HTTP/WebSocket and UI

The API keeps `/api/v1`, loopback binding, origin validation and strict
Pydantic/Zod boundaries. P3 adds:

- `GET/POST/PUT/DELETE /games`, `GET /games/active`,
  `POST /games/{id}/test-match`;
- `GET /foreground`, `GET/PUT /automation`;
- `GET/PUT /compatibility`, `GET/PUT /mappings`, `GET/PUT /chords`;
- `GET /diagnostics/conflicts`.

Versioned events include `game.foreground_changed`, `game.detected`,
`game.activated`, `game.deactivated`, `game.rule_applied`,
`compatibility.changed`, `game.conflict_detected`, `automation.changed` and
`synthetic.release`. Unknown future events remain safely ignorable in the
frontend.

`/games` presents foreground identity, active game/profile/origin, realtime
automation, Native/Remap/Virtual mode, exit policy, registry editing and match
explanations, mappings, chords, conflict warnings and explicit Virtual
unavailability. Offline, pending, stale, loading, error and reconnect states
remain visible without a reload.

## Required evidence split

1. Automated Linux evidence: static checks, unit/API tests, package build and
   frontend tests.
2. Source-level evidence: boundary, wired-only, Tauri permission and safety
   audits.
3. Windows evidence: Win32 imports, packaged build and real foreground/
   `SendInput` behavior.
4. Physical evidence: DualSense connected by USB, lifecycle, input, profile,
   remap and teardown smoke checks.
5. Future provider evidence: separate decision and validation for any
   virtual-controller provider; it is not a P3 acceptance condition.

The P3 technical handoff may be `READY FOR INDEPENDENT REVIEW` only after the
automated and source-level gates are recorded. Windows and physical USB
validation remain `HARDWARE VALIDATION PENDING` in this environment.
