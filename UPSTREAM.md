# Upstream baseline

DS5Forge started from the open-source project `Casliyan/DS5companion`.

- Repository: https://github.com/Casliyan/DS5companion
- Branch: `main`
- Baseline commit: `0a77920cf9a59d2655f6f9915197ead3cbda08e0`
- Upstream commit date: 2026-08-13
- Imported into DS5Forge baseline: 2026-09-14
- License: MIT
- Upstream copyright: Copyright (c) 2026 Casliyan

## Imported baseline

The maintainable source baseline is preserved under `source/`, including:

- Python application/runtime code;
- WASAPI audio-to-rumble engine;
- controller lifecycle implementation;
- touchpad/mouse implementation;
- legacy `customtkinter` GUI;
- default configuration and haptics profiles;
- PyInstaller build definition and source launcher.

## Deliberately not imported

The upstream prebuilt executable under `dualsensecompanionexe/` is not copied into DS5Forge. It is a compiled artifact and is not required to inspect or evolve the source.

Binary branding/icon assets are also not required for the D0 source baseline. The upstream build already tolerates a missing icon, and branding will be revisited during DS5Forge productization.

## Preservation rule

P0 refactoring must preserve the behavior represented by this baseline before intentionally changing it. The Windows/USB regression checklist lives in `docs/D0_SMOKE_CHECKLIST.md`.
