# DS5Forge Release Candidate Validation

This record starts with `0.4.0-rc.1`. It separates CI evidence from real Windows and physical DualSense evidence. No runtime/hardware item is considered proven by mocks or packaging alone.

## RC policy

- RC versions follow SemVer prerelease ordering: `0.4.0-rc.1`, `0.4.0-rc.2`, then `0.4.0`.
- No new product features are added during RC stabilization.
- Bluetooth/wireless remains out of scope.
- Every RC is built from a signed `vX.Y.Z-rc.N` tag by the Windows release workflow.
- Prerelease installations read updater metadata from the fixed GitHub Release channel `update-rc`.
- The final stable release reads `releases/latest`; publishing stable also refreshes `update-rc` so RC installs can promote to stable.
- Tauri updater signing is not Windows Authenticode code signing. Internal RC installers may still show Windows/SmartScreen publisher warnings until executable code signing is added later.

## Pre-tag automated gate — `0.4.0-rc.1`

- [ ] `python scripts/validate_versions.py --expected v0.4.0-rc.1`
- [ ] Ruff format/check
- [ ] mypy
- [ ] compileall
- [ ] pytest
- [ ] Python wheel build
- [ ] frontend Prettier
- [ ] frontend ESLint
- [ ] frontend TypeScript
- [ ] frontend Vitest
- [ ] frontend production build
- [ ] production npm audit
- [ ] Playwright
- [ ] PyInstaller Windows packaging CI
- [ ] Tauri Windows NSIS build CI
- [ ] `cargo fmt --check`
- [ ] `cargo check --all-targets --all-features`
- [ ] `cargo clippy --all-targets --all-features -- -D warnings`
- [ ] wired-only implementation audit

## Local preflight recorded — 2026-09-15

- `validate_versions.py --expected v0.4.0-rc.1`: PASS.
- Ruff format/check: PASS, 86 Python files formatted.
- mypy `source/dualsense_companion scripts`: PASS, 64 source files.
- Python compileall: PASS.
- pytest: **135 passed**.
- Python wheel: PASS; PEP 440 artifact name `ds5forge-0.4.0rc1-py3-none-any.whl`.
- Frontend Prettier, ESLint and TypeScript: PASS.
- Vitest: **41 passed** across 12 files.
- Vite production build: PASS.
- `npm audit --omit=dev`: PASS, **0 vulnerabilities**.
- Playwright Chromium: **11 passed**.
- Release workflow YAML parse: PASS.
- npm/package-lock version sync: PASS, `0.4.0-rc.1`.
- Windows-host Cargo metadata with locked manifest: PASS, package version `0.4.0-rc.1`.
- `git diff --check`: PASS.
- Native Windows PyInstaller/Tauri/Rust CI remains pending until the RC prep commit is pushed.

## Release publication gate

- [ ] Tauri updater signing keypair generated outside the repository.
- [ ] private key backed up securely; it is not pasted into chat, committed or logged.
- [ ] `TAURI_SIGNING_PRIVATE_KEY` configured as GitHub Actions secret.
- [ ] `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` configured as GitHub Actions secret when a password is used.
- [ ] `TAURI_SIGNING_PUBLIC_KEY` configured as GitHub Actions secret.
- [ ] tag `v0.4.0-rc.1` points to the reviewed RC commit.
- [ ] Windows release workflow succeeds.
- [ ] versioned GitHub prerelease exists and contains NSIS installer, `.sig`, `latest.json`, `SHA256SUMS.txt` and packaged core artifact.
- [ ] `update-rc/latest.json` resolves to the same RC version and versioned installer URL.
- [ ] checksum verification succeeds for downloaded artifacts.

## Real Windows install/lifecycle — user evidence required

Record Windows edition/version, architecture, DS5Forge installer checksum and exact RC version.

- [ ] clean per-user install as a normal user.
- [ ] first launch reaches application-ready state.
- [ ] packaged Python core starts without a system Python dependency.
- [ ] closing the window hides to tray rather than orphaning/duplicating processes.
- [ ] tray Open, Show/Hide and Quit work.
- [ ] second app launch focuses/restores the existing instance and does not spawn a second core.
- [ ] autostart is OFF by default.
- [ ] autostart enable -> reboot/login -> launch works once.
- [ ] autostart disable is reversible.
- [ ] Restart Core performs bounded teardown and returns to ready state.
- [ ] Quit leaves no DS5Forge core process and no loopback listener on port 8765.
- [ ] reinstall/repair over the same RC is predictable.
- [ ] uninstall removes the application while preserving the documented user-data locations.
- [ ] uninstall leaves no DS5Forge process, tunnel or listener.

## Physical DualSense USB — user evidence required

- [ ] controller is connected by USB and identified correctly.
- [ ] disconnect/reconnect works without restarting the desktop app.
- [ ] buttons, sticks and triggers update correctly.
- [ ] touchpad telemetry and configured mouse/gesture behavior work.
- [ ] lightbar controls apply/reset safely where supported.
- [ ] adaptive trigger previews start, time out/stop and neutralize.
- [ ] haptics test bench starts/stops and neutralizes.
- [ ] profiles apply and revert without stale output.
- [ ] game/foreground automation changes/restores profiles as expected.
- [ ] Native remains the default compatibility mode.
- [ ] Remap is explicit and synthetic keys/buttons are released on teardown.
- [ ] disconnect, Restart Core, Quit and uninstall leave motors/triggers/synthetic output neutral.
- [ ] at least one real game with native DualSense support is exercised in Native mode.
- [ ] at least one relevant game/remap scenario is exercised without double input.

## Remote Access — user/external-device evidence required

- [ ] Remote Access is OFF immediately after install.
- [ ] OFF state has no active remote session and no cloudflared child managed by DS5Forge.
- [ ] missing cloudflared is diagnosed without automatic installation.
- [ ] valid tunnel configuration is explicit and does not expose raw credentials in support data.
- [ ] pairing challenge is initiated locally and can be used once.
- [ ] remote session works from a phone/device outside the PC browser context.
- [ ] wrong Origin is rejected.
- [ ] missing/invalid session cookie is rejected.
- [ ] session revocation blocks subsequent access.
- [ ] disabling Remote Access revokes sessions and stops the tunnel.
- [ ] quitting DS5Forge stops the managed tunnel.

## Updater end-to-end — requires `0.4.0-rc.2`

After `rc.1` runtime validation, create `0.4.0-rc.2` only from stabilization fixes.

- [ ] installed `rc.1` detects `rc.2` through `update-rc`.
- [ ] detached signature is accepted.
- [ ] core is neutralized/stopped before updater installation starts.
- [ ] passive Windows update completes.
- [ ] updated app reports `0.4.0-rc.2` and starts the packaged core.
- [ ] profiles/config/user data remain intact.
- [ ] invalid signature/update is rejected and current install remains usable.
- [ ] downgrade metadata is rejected.
- [ ] after stable `0.4.0` is published, an installed RC detects and can promote to stable.

## GO rule

`v0.4.0` stable is allowed only when CI, Windows lifecycle, physical USB, Remote Access and RC-to-RC updater evidence are green, with stabilization bugs closed or explicitly accepted. Until then report `RELEASE CANDIDATE — WINDOWS/HARDWARE VALIDATION PENDING`.
