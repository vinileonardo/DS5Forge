# ADR P4 — Windows Packaging

## Decision

Use Tauri 2 as the Windows shell and NSIS as the only P4 production installer.
Bundle a headless PyInstaller `DS5ForgeCore` sidecar. Install per-user when
the target supports it; provide predictable shortcuts, reinstall and upgrade.

## Rationale and constraints

The sidecar keeps Python and controller dependencies out of the end-user
machine. Tauri owns lifecycle, tray, single-instance, autostart and updater;
the Python core owns hardware. Capabilities allow only the named sidecar
command and official product plugins. There is no arbitrary shell, filesystem
or inbound HTTP permission.

Uninstall preserves config, profiles, games and logs. Removing those data is a
separate explicit action. NSIS and sidecar behavior require real Windows
validation before a release GO.
