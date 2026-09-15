# Upstream to P0 migration note

The P0 starting point is the source snapshot recorded in `UPSTREAM.md`.
`source/dualsense_companion/resources/` and the baseline PyInstaller flow are
preserved. The compiled upstream executable is intentionally not part of the
maintained source tree.

| Upstream surface | P0 owner | Compatibility |
| --- | --- | --- |
| `controller.py` | `core/controller_service.py` + Windows adapter | old import is a shim |
| `audio_rumble.py` | `core/dsp.py` + `core/haptics_service.py` | DSP names are re-exported |
| `touch_mouse.py` | `core/touchpad.py` + mouse adapter | semantic actions precede SendInput |
| `state.py` | `core/state_store.py` + `CoreFacade` | `AppState` is read-only projection |
| `app.py` | `ApplicationRuntime` | GUI remains available as a client |
| config/profile files | `ConfigRepository` | schema v1 adds a version field; bundled profile names become reserved/read-only |

No P0 tuning redesign is intended. The haptics mapping, filter coefficients,
envelope timings and touch gestures are carried over into pure/testable code.
The intentional behavior changes are safety/ownership changes: invalid config
is rejected or normalized, disconnect/shutdown neutralizes output, runtime
exceptions become diagnostics instead of silent `pass` paths, and bundled
profiles are immutable authority.

Bundled profile names are reserved case-insensitively. If an older upstream
installation contains a user file with the same name as a bundled preset, P0
does not delete or rewrite that file, but it does not allow it to override the
bundled preset. Rename any customized same-name legacy file to a unique user
profile name before editing it through P0.
