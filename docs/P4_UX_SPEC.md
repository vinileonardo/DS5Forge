# P4 UX Specification

P4 extends the existing SPA in place. It does not create a second frontend or
redesign the P0-P3 surfaces.

## Startup and shell

The desktop shows an explicit startup sequence: desktop starting, core
starting, core ready, application ready, or a named error/timeout. A crash
shows the attempt count and a safe `Restart core` action. The app remains
usable for diagnostics when the controller is absent; absent hardware is not
presented as success.

The tray contains Open, a short core status, Show/Hide and Quit. A second
process focuses/restores the first window and never starts a second core.
Closing the window hides to tray; Quit performs coordinated teardown.

## Settings

Settings contains the existing Appearance and controller-button controls plus:

- Desktop: version, shell/core lifecycle and Restart core.
- Startup: reversible Windows autostart, disabled by default.
- Updates: signed HTTPS check, download progress, non-destructive failure and
  restart/apply feedback.
- Remote Access: one-time pairing, origin display, session list/revoke,
  explicit cloudflared validation/start/stop and an obvious Disable action.
  Remote OFF is the empty/default state; tunnel configuration is never
  downloaded or started implicitly.
- Advanced: wired-only scope, Virtual unavailable explanation and Support
  Bundle export.

All actions are mobile-viewport safe, keyboard reachable and use existing
cards/buttons/tokens. Pairing codes are visible only in the local pairing
flow; tokens never appear in URLs, browser events, logs or telemetry.

## Diagnostics

Diagnostics shows guided checks with one of `healthy`, `warning`, `unavailable`,
`failed` or `not_applicable`, an explanation and an actionable next step. A
Support Bundle button confirms bounded, sanitized export. Remote/tunnel status
is shown separately from local API and USB state.
