# DS5Forge — P1 UX Specification

## 1. Product intent

P1 should make DS5Forge feel like a focused Windows controller utility, not a generic admin dashboard and not a game-launcher clone.

The interface should communicate three things immediately:

1. whether the local DS5Forge core is reachable;
2. whether a wired DualSense is actually connected and healthy;
3. what DS5Forge is currently doing to the controller.

The UI is a client of the local core. It must never imply successful hardware state solely because the frontend itself is running.

## 2. Visual direction

Default visual language: dark, premium, technical and restrained.

Recommended foundation tokens:

- app background: near-black graphite;
- primary surface: deep charcoal/navy;
- elevated surface: slightly lighter neutral;
- borders: subtle cool-gray;
- main text: near-white;
- secondary text: cool gray;
- primary accent: electric blue;
- secondary accent: restrained violet/indigo;
- success: green;
- warning: amber;
- danger: red/rose.

Do not overuse gradients, glassmorphism, glow, animated neon, gaming-RGB motifs or translucent cards. Small accent glows are acceptable only where they reinforce controller/connection state and remain subtle.

The interface should feel closer to a polished native PC settings/control application than to a SaaS analytics product.

## 3. Layout

### Desktop

Target the main experience at desktop widths first.

Suggested shell:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ DS5Forge                                      USB Controller • Connected │
├───────────────┬─────────────────────────────────────────────────────────┤
│ Overview      │                                                         │
│ Haptics       │                  active page                            │
│ Touchpad      │                                                         │
│ Profiles      │                                                         │
│ Diagnostics   │                                                         │
│ Settings      │                                                         │
│               │                                                         │
│ Core status   │                                                         │
└───────────────┴─────────────────────────────────────────────────────────┘
```

- persistent left rail/sidebar at desktop widths;
- sidebar should be compact enough to preserve content space;
- route title and meaningful status live near the top of the content area;
- avoid a dense top navigation bar plus sidebar at the same time;
- cards/panels should be used for real grouping, not every single field.

### Mobile / narrow window

P1 does not need to become a phone-first product, but it must remain usable when the Tauri window is narrow or when the browser is opened on a phone.

- collapse sidebar into a compact drawer/bottom navigation pattern;
- forms become single-column;
- avoid horizontal scrolling for normal content;
- keep connection/offline state visible;
- do not hide critical actions behind hover-only interactions.

## 4. Global status semantics

The frontend has two independent status dimensions and must not conflate them:

### Core reachability

- `online`: HTTP/WS core reachable;
- `reconnecting`: previously reachable, connection temporarily lost, reconnect attempts active;
- `offline`: core currently unreachable;
- `protocol_error`: core is reachable but payload/version cannot be trusted.

### Controller lifecycle

Use the P0 values exactly:

- `disconnected`
- `connecting`
- `connected`
- `reconnecting`
- `stopping`
- `error`

Rules:

- frontend `online` + controller `disconnected` is a valid state;
- frontend `offline` must not continue displaying a green `connected` controller as if it were current truth;
- stale cached controller values may be shown only with an obvious stale/offline treatment;
- `error` must include the safe structured error message when available;
- do not represent `connecting`/`reconnecting` as success.

Every status uses text/iconography in addition to color.

## 5. Overview page

Purpose: answer “Is my DualSense connected, healthy and configured the way I expect?” in a few seconds.

Recommended sections:

### Controller hero/status

Show:

- connection state;
- model;
- USB transport;
- battery percentage;
- charging state if known;
- active profile.

When disconnected, the hero should become a connection/waiting state rather than showing empty metric cards.

### Quick controls

Only controls supported now:

- Haptics enabled/disabled;
- Touchpad enabled/disabled.

Actions must show pending state until server confirmation.

### Runtime summary

- current audio capture status/device;
- capabilities summary;
- health/degraded count;
- last meaningful error if present.

Avoid exposing P2 controls such as lightbar/adaptive triggers on Overview.

## 6. Haptics page

Purpose: make the existing P0 audio-to-rumble system understandable without hiding advanced tuning.

Recommended hierarchy:

### Primary controls

- master enabled toggle;
- active profile;
- bounded “Test rumble” action.

### Tuning groups

Group existing fields conceptually, for example:

- Frequency response: heavy cutoff, texture center;
- Envelope: fast attack/release, baseline attack/release;
- Detection/gating: gate, impact level, drive gate, texture gate multiplier;
- Transient shaping: transient minimum, gain, weight;
- Output shaping: gamma, min rumble, max rumble.

Each field should include a concise human explanation and unit where meaningful.

Advanced values should not occupy the full first viewport. Use collapsible/sectioned advanced tuning while keeping all current values editable.

Save behavior:

- dirty state should be visible;
- save/apply is explicit;
- server field errors appear next to the corresponding control when possible;
- successful save uses restrained confirmation, not a blocking modal.

## 7. Touchpad page

Purpose: configure the current mouse/gesture behavior.

Show:

- live enabled toggle;
- enabled on start;
- pointer speed;
- acceleration;
- acceleration cap;
- scroll speed;
- tap-to-click.

Explain that this maps the DualSense touchpad to Windows pointer/gesture behavior.

No gesture map/editor and no live touch visualizer in P1.

## 8. Profiles page

Purpose: make existing haptic presets easy to understand and safe to manage.

Profile list/card/table rows should show:

- profile name;
- bundled or user-created source;
- editable/read-only state;
- active state.

Actions:

- Apply/Load;
- Save current haptics as new user profile;
- Delete editable user profile.

Bundled profiles are immutable. Do not show enabled destructive controls for them.

Use a confirmation dialog for delete with the exact profile name.

## 9. Diagnostics page

Purpose: help the user/reviewer distinguish frontend, core, controller and audio failures.

Recommended sections:

### Core

- reachable state;
- WebSocket state;
- last reconnect attempt/outcome if useful;
- API base endpoint (read-only).

### Controller

- lifecycle;
- identity where available;
- sequence/update timestamp.

### Subsystems

Render `health.subsystems` and `health.degraded` clearly.

### Audio

- capture state;
- current device;
- error.

### Errors

- code;
- safe message;
- recoverable status;
- useful non-sensitive fields.

### Session event timeline

Optional bounded client-side timeline for current-session events only. Keep a fixed maximum and newest-first ordering. This is not a replacement for P4 log export.

## 10. Settings page

Only expose real supported settings.

### Appearance

- Light;
- Dark;
- Liquid Glass if preserved from the existing contract.

The new product styling should be designed dark-first, but persisted selection remains authoritative.

### Microphone button behavior

Provide readable labels for the existing values:

- `master` — toggles the master behavior defined by the current core;
- `rumble` — controls rumble/haptics;
- `trackpad` — controls touchpad behavior.

Use the core contract values on the wire; labels can be user-friendly.

### Local service information

Show API/core address as informational diagnostics. Do not expose an arbitrary internet URL field in P1.

## 11. Feedback states

Every async surface needs explicit states:

- initial loading;
- action pending;
- success where confirmation helps;
- structured validation error;
- backend/core offline;
- controller unavailable;
- feature unavailable due to capability/state.

Avoid indefinite skeletons or spinners without explanatory text when the core is offline.

## 12. Empty and disconnected states

When no controller is attached:

- the app remains useful for configuration/profiles/diagnostics where supported;
- Overview clearly says DS5Forge is waiting for a wired DualSense;
- do not recommend Bluetooth pairing;
- hardware-only actions are disabled with a reason;
- the UI should automatically recover when the controller reconnects.

When the Python core itself is offline:

- show a global local-service-offline state;
- provide concise instructions to start the local core during development;
- retry automatically;
- do not fabricate state from defaults as if it came from hardware.

## 13. Interaction rules

- toggles that send commands become temporarily disabled/pending until response;
- avoid double-submit;
- destructive actions require confirmation;
- slider controls should also have a precise numeric input when useful;
- keyboard users must be able to reach every primary action;
- tooltips must not contain information required to understand an error/action; important help text should remain visible or available through accessible descriptions.

## 14. Motion

Use motion only for orientation and state transitions.

Acceptable:

- short page/content fade/translate;
- connection-state indicator transition;
- subtle progress/pending feedback.

Avoid:

- continuous decorative animation;
- heavy parallax;
- glowing pulsing panels;
- controller-themed motion that competes with state information.

Honor `prefers-reduced-motion`.

## 15. Accessibility baseline

P1 baseline:

- semantic headings and landmarks;
- labels for every form field;
- programmatic descriptions for units/help;
- keyboard navigation;
- visible focus rings;
- dialogs trap focus and return focus on close;
- status is never color-only;
- contrast suitable for normal text/actions;
- live status updates should avoid noisy screen-reader announcements.

## 16. Design anti-patterns

Do not produce:

- a generic four-card KPI dashboard;
- fake metrics not present in P0;
- neon gamer/RGB overload;
- a giant controller illustration replacing useful status;
- a settings page made of dozens of disconnected cards;
- a mobile-first bottom-nav-only desktop UI;
- hover-only actions;
- hidden backend failures;
- raw JSON dumps as the primary diagnostics experience;
- P2/P3 controls presented as disabled “coming soon” clutter.

## 17. P1 visual acceptance

The UI is acceptable when:

- the main controller state is understandable within seconds;
- disconnected/offline/degraded states are visually distinct from healthy connected state;
- the desktop layout feels intentional at 1366x768 and 1920x1080;
- narrow/mobile layout remains usable;
- Haptics and Touchpad forms are understandable without reading source code;
- bundled vs user profiles are obvious;
- diagnostics help locate failures rather than merely expose data;
- the same SPA works in browser and Tauri without visual forks.
