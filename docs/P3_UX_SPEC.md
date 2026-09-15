# DS5Forge — P3 UX Specification

## Route and navigation

Add `Games` to the existing primary and compact navigation at `/games`. Keep
the P1/P2 shell, typography, spacing, status pills, cards and canonical
design-system components. This is a focused compatibility control surface,
not a redesign of the application.

## Page contract

### Foreground card

Show the current executable name, PID, optional full path when available,
window title as diagnostic context, observation timestamp and a recoverable
diagnostic when process inspection is unavailable. Identity and rule matching
must visibly be executable-based; a mutable title must never be presented as
the game identity.

### Active game card

Show `No active game` when no enabled rule matches. When active, show game name,
configured executable identities, active profile, profile origin (`manual` or `automatic`), last
match explanation and the automation transition state. Updates arrive from
the WebSocket projection without a page reload.

### Automation and exit policy

Provide an explicit on/off control and an exit-policy selector:

- Restore previous profile (default);
- Apply Default profile;
- Keep current state.

Disable commands while the core is stale/offline. Show a pending state while a
request is in flight. A manual profile or compatibility change must surface a
manual-override indicator and explain that automatic reapplication waits for a
real foreground transition.

### Compatibility card

Show the current mode as `Native`, `Remap` or `Virtual / XInput`. Native is the
safe default and creates no synthetic output. Remap is described as validated
keyboard/mouse output without XInput and must visibly warn that physical
DualSense input remains visible, so a game/Steam configuration may still create
double input. Logical output remains reserved until an
explicit production adapter exists. Virtual remains visible as a deliberate
choice, but the selector and notice must clearly say `Unavailable` when no
approved provider with reliable physical suppression exists. The card always
shows physical input visibility, virtual input activity, suppression and
double-input risk; it must never imply a successful mode change after a
rejected request.

### Registry editor

List registered rules with enabled/disabled state, one-or-more executables,
optional exact path for single-executable rules, profile and compatibility mode. Support add, edit, remove and `Test
match`. The test result must include matched/not matched, reason and the
evaluated rule details. Invalid or duplicate input is reported from the
structured server error; optimistic local state must not pretend persistence.

### Mappings and chords

Provide compact editors for controller input → validated keyboard/mouse output
and for two-or-more-input chords. Keyboard output accepts a single key or a
bounded `+` combination such as `CTRL+SHIFT+S`; overlapping combinations must
not release shared modifiers prematurely. Mouse output includes left/right/
middle plus Mouse4/Mouse5. Display the configured scope when present. Existing
mapping/chord IDs are immutable while editing and both lists provide explicit
removal actions so an edit cannot accidentally create a duplicate entry.
Explain that chords have precedence during their bounded window, that a simple
mapping waits for the longest still-valid candidate window, and that ambiguous
subset chords in overlapping scopes are rejected.

### Conflict diagnostics

Show process-name evidence for Steam and configured remappers. The Steam copy
must say: “Steam is running. Steam Input may affect this game depending on its
configuration.” Do not label Steam Input as active without evidence. Do not
offer kill, disable or external configuration actions.

## State matrix

| State | Required presentation |
| --- | --- |
| Loading | Page heading plus loading indicator; no false empty registry claim |
| Pending | Disable the affected control and show its pending label |
| Online/realtime | Fresh status pill and live foreground/active-game projection |
| Stale | Warning status, explain that the last snapshot is retained, disable output commands |
| Offline | Local-core warning, retain last safe registry data if available |
| Error | Structured message with recoverable context; preserve drafts |
| Reconnecting | Visible reconnect status; active game updates after snapshot recovery |
| Virtual unavailable | Persistent explicit notice; Native/Remap remain unchanged after rejection |
| No game | Desktop/unavailable foreground and no active game, not an error |

## Accessibility and safety

Use real labels for all fields, keyboard-focusable controls, semantic headings,
status/alert roles for diagnostics and readable text for mode/policy choices.
Destructive game removal uses confirmation. No UI action accesses controller
objects, process handles or native APIs directly. No Bluetooth/wireless,
driver, installer or external-process control affordance is exposed.
