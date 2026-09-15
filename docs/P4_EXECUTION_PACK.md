# DS5Forge P4 Execution Pack

## Baseline and handoff

P4 is based exclusively on `14ddf16ba15f980e9ffe3f94c0aeb4e70bebbf03`
(`feat/p3-compat-games-automation`). Work is isolated on
`feat/p4-productization-release-remote`. The existing untracked
`docs/P2_REVIEW_SCOPE.json` and `docs/P2_REVIEW_SCOPE_V2.json` are preserved.

This sprint does not commit, push, merge, publish a release, install a driver,
or claim Windows/USB proof. The final handoff is
`READY FOR INDEPENDENT REVIEW — WINDOWS/HARDWARE VALIDATION PENDING` when the
available source and automated gates are green.

## Binding boundaries

- P0-P4 are USB/wired only. No Bluetooth, wireless transport, dongle,
  wireless pairing, or wireless tuning is implemented.
- Python core remains the sole hardware authority and binds its API to
  loopback. The desktop shell supervises the packaged headless sidecar.
- Native is the default; Remap is explicit; Virtual remains unavailable and
  no driver is installed or bundled.
- Remote access is OFF by default. Pairing is initiated locally and creates a
  one-use challenge; sessions persist only a digest/reference and use secure
  HttpOnly cookies.
- `cloudflared` is an explicitly installed user dependency. DS5Forge never
  downloads, installs, upgrades, or logs its token.

## Deliverables

1. `VERSION` is the canonical release value (`0.4.0` for this P4 baseline).
   `scripts/validate_versions.py` checks Python, frontend, Cargo and Tauri
   metadata.
2. `source/build.spec` produces the headless `DS5ForgeCore` PyInstaller
   sidecar. It does not require Python on the target Windows machine.
3. `core/lifecycle.py`, `core/diagnostics.py`, `core/remote.py`,
   `core/tunnel.py`, `core/updates.py` and `core/support_bundle.py` provide
   bounded, testable product contracts.
4. `/api/v1` exposes app info, lifecycle/restart, guided diagnostics, support
   bundle, update metadata validation, remote pairing/session control and
   tunnel status/control.
5. Tauri has single-instance focus, tray Open/status/Show-Hide/Quit,
   autostart integration (OFF by default), sidecar supervision, updater
   initialization, NSIS per-user bundle configuration and minimal capability
   scope.
6. Release scripts build sidecar/desktop/NSIS, validate signatures and emit
   checksums/static updater metadata. The post-P4 release-candidate hardening
   promotes signed tags into versioned GitHub Releases. Prereleases publish
   updater metadata through the fixed `update-rc` channel; stable releases use
   `releases/latest` and also refresh `update-rc` once to migrate RC installs.

## Recovery and teardown

Startup polls `/api/v1/health` with a bounded timeout. A child crash enters an
explicit crash state and retries with a bounded backoff/attempt limit. Manual
Restart core releases synthetic keyboard/mouse output, haptics, triggers,
motors, previews and automation before starting again. Quit, update and
uninstall preserve user data and use the same release path. Uninstall keeps
config, profiles, games and logs; a future separate data-removal action must be
explicit.

## Evidence split

- Linux/source: Python, frontend and static security/boundary gates.
- Native Windows: Tauri, NSIS, sidecar, tray, autostart, single-instance,
  upgrade, uninstall and orphan-process proof.
- Physical: DualSense USB lifecycle, haptics, touchpad and teardown proof.

The latter two are not inferred from mocks. In this environment they remain
`WINDOWS VALIDATION PENDING` and `HARDWARE VALIDATION PENDING`.
