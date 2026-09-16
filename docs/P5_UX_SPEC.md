# P5 UX specification — Compatibility, Games and trust states

## Trust rules

The interface must distinguish fresh authority state from stale transport
state. When the WebSocket is reconnecting or offline, controller, foreground,
active game, automation and Exclusive values are not rendered as current. The
page may show the last payload as historical context, but labels it stale and
disables commands that require fresh authority.

Native DualSense is the default. Exclusive, remapping and generated reactive
effects require explicit user action and a visible capability explanation.

## Games

The Games page has four user tasks:

1. choose a running/recent executable candidate;
2. pick an `.exe` through the native Tauri picker (with a browser file-input
   fallback), generating a stable initial ID from the executable name;
3. select a real saved profile from a dropdown and explain Native, Exclusive
   and Remapping modes;
4. choose that game's adaptive-trigger behavior: `native` (default, untouched),
   `reactive` (explicit opt-in to a clearly DS5Forge-generated effect) or `off`
   (neutralize DS5Forge trigger output);
5. open Advanced to review mappings and chords before saving.

Candidates are suggestions only. Saving a game remains explicit, executable
identity is separate from window-title diagnostics, and running candidates take
precedence over duplicate recent entries. The browser file-input fallback stores
only the executable identity (`executable_path=null`) because a basename is not
a verified absolute path. The Exclusive toggle is actionable only when the
complete capability is operational, not merely present.

Stick calibration is explained as applying to DS5Forge Exclusive virtual
mirroring and visualization/profile metadata; Native physical input remains
untouched and Remap stays a digital keyboard/mouse mapper.

## Topbar and controller status

The authenticated shell topbar shows the active profile, input origin and mode.
The origin is USB when a fresh connected snapshot says so; stale data does not
masquerade as a current USB connection. Exclusive status includes provider
availability, output-report support, suppression verification and duplicate-input
risk. A warning is shown whenever physical visibility is not verified.

## Language and first paint

`pt-BR` and `en-US` are typed, parity-checked dictionaries behind one
app-global provider. Changing the language in Settings immediately updates the
shell and the mounted page without a reload. Locale selection is persisted
locally and remains usable offline. `pt-BR` uses natural product copy
(`Modo exclusivo`, `provedor`, `origem/verificação`, `Risco de entrada
duplicada`) rather than mixed English strings. A small pre-React bootstrap reads
the locale and the last confirmed theme before mounting; Dark is the safe
default. React synchronizes after bootstrap without flashing a different theme
or overwriting an absent preference.

## Updater and Remote Access

The updater communicates `checking`, `downloading`, `installing` and automatic
relaunch states. Browser fallback copy explains that the shell must be
restarted manually. Remote Access is visually grouped under Settings →
Advanced; its origin enforcement, cookies, pairing, revocation and tunnel
teardown contracts are unchanged.

All disabled states require an actionable reason. Error messages use the typed
API error shape and do not expose tokens, provider ownership tokens or local
credentials. The controller SVG and touch points remain accessible with text
labels and state announcements; generated trigger effects are explicitly
identified as DS5Forge-generated.
