# DS5Forge — P2 Controller Lab UX Specification

## Intent

Controller Lab is a safe instrument panel for a connected wired DualSense.
It should make raw controller behavior legible, distinguish current server
truth from stale data, and make every output experiment reversible. It is not
a remapping editor or a virtual-controller setup screen.

## Route and tabs

Use one primary `/controller` route with four internal tabs:

- **Input** — live controller state and touch telemetry;
- **Triggers** — adaptive-trigger configuration and bounded preview;
- **Lighting** — lightbar color, apply and reset;
- **Sticks** — two XY planes, calibration metadata and deadzone preview.

The route remains reachable when the core is offline so the user sees why
controls are disabled. Tabs do not imply hardware support merely by existing.

## Input tab

Show a compact controller silhouette or grouped control matrix for face
buttons, D-pad, shoulders, options/share, PS, touchpad, microphone and L3/R3.
Pressed state uses text/shape plus color. Show L2/R2 analog fill and digital
state, left/right stick positions in XY planes, and zero/one/two live touch
points in normalized touchpad coordinates.

Each reading includes an update age/sequence indicator. When the WebSocket is
stale or the controller is disconnected, freeze the last sample only with an
obvious stale/offline treatment and disable output controls.

## Triggers tab

Present left and right trigger effects as separate cards with a small preset
set: Off, rigid/continuous resistance and pulse where the connected runtime
reports support. Show validated numeric parameters and a bounded preview
button. While a preview is active, lock duplicate preview submissions and show
the expiry countdown. Timeout, cancel, disconnect and reconnect all surface a
neutral Off state.

If adaptive triggers are unavailable, show the adapter/library reason and keep
the form visible as an explanation, not as an enabled fake control.

## Lighting tab

Use a color input plus explicit RGB values and Apply, Reset and status text.
The preview swatch is local presentation only; the applied state is server
truth. Disable Apply/Reset when the core or lightbar capability is unavailable.

## Sticks tab

Render two labeled XY planes with crosshairs and deadzone rings. Provide
validated metadata fields for left/right deadzone and center calibration, with
Reset draft and Save metadata actions. Explain directly:

> Stick calibration and deadzone affect DS5Forge visualization and profile
> metadata only. They do not modify native game input.

## Touchpad and haptics upgrades

The existing Touchpad page gains live points, button state and the real gesture
settings exposed by the core. The Haptics page gains a bounded test bench with
left/right intensity, duration, pending lock and automatic neutralization
status. Existing P0/P1 controls and behavior stay intact.

## Safety semantics

No successful-looking optimistic hardware state is shown before server
confirmation. Unsupported capabilities return a structured notice. Reconnect
invalidates stale output controls until a fresh snapshot arrives. Profile
import validates in memory first; malformed, oversized, incompatible or
unconfirmed overwrite attempts leave current state unchanged.
