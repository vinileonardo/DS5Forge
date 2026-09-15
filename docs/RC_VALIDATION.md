# DS5Forge Release Candidate Validation

This record starts with `0.4.0-rc.1`. It separates CI evidence from real Windows and physical DualSense evidence. No runtime/hardware item is considered proven by mocks or packaging alone.

## RC policy

- RC versions follow SemVer prerelease ordering: `0.4.0-rc.1`, `0.4.0-rc.2`, `0.4.0-rc.3`, `0.4.0-rc.4`, `0.4.0-rc.5`, then further RCs only if validation still finds blockers before `0.4.0`.
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

## RC1 Windows findings — 2026-09-15

The first installed `0.4.0-rc.1` provided real evidence that packaging CI alone was insufficient:

- installer checksum matched the published release artifact and installation completed per-user.
- `ds5forge.exe` launched with PE subsystem `3` (Windows CUI), which created an unwanted visible console window.
- `DS5ForgeCore.exe` was correctly built with PE subsystem `2` (Windows GUI).
- the installed sidecar existed as `C:\\Users\\Vini\\AppData\\Local\\DS5Forge\\ds5forge-core.exe`, but the Rust shell requested `binaries/ds5forge-core`; Tauri v2 Rust sidecar lookup expects the embedded binary basename.
- no core process remained alive and TCP port `8765` was closed, so the frontend correctly reported `Local core offline`.
- RC1 could not exercise the in-app updater because the Settings page was entirely hidden when the core was offline. This is an RC1 recovery-UX defect, not updater success; later RC validation must establish a source version whose updater remains reachable even when realtime transport is degraded.

## RC2 stabilization gate

- [ ] canonical version is `0.4.0-rc.2` across Python, npm/package-lock and Tauri/Cargo manifests.
- [ ] Tauri Rust sidecar lookup uses `sidecar("ds5forge-core")` while `externalBin` remains `binaries/ds5forge-core`.
- [ ] release binary entrypoint (`main.rs`) declares `windows_subsystem = "windows"` for non-debug builds.
- [ ] Windows CI verifies `ds5forge.exe` PE subsystem is GUI (`2`).
- [ ] Windows CI verifies `DS5ForgeCore.exe` PE subsystem is GUI (`2`).
- [ ] Python tests, frontend checks, Playwright and native Rust checks are green.
- [ ] signed `v0.4.0-rc.2` release refreshes `update-rc/latest.json` to RC2.

## RC2 Windows findings — 2026-09-15

Real RC2 validation proved the sidecar-launch and PE-subsystem fixes but exposed a second packaging defect:

- `ds5forge.exe` reported `0.4.0-rc.2` and no visible console window opened.
- the Tauri shell successfully launched the packaged `ds5forge-core.exe`; the core remained alive and listened on `127.0.0.1:8765`.
- `/api/v1/health`, `/state`, `/config` and `/profiles` returned HTTP `200` with the installed WebView origin `http://tauri.localhost` allowed by CORS.
- the health/state response reported the wired DualSense connected and core/controller/audio/touchpad subsystems ready/healthy.
- a browser-like WebSocket upgrade to `/api/v1/ws` returned HTTP `404` instead of `101 Switching Protocols`, even though the FastAPI route exists in source.
- root cause: `uvicorn` was bundled without an explicit WebSocket protocol runtime (`websockets`/`wsproto`); ASGI-level tests exercised the route directly and therefore could not detect the missing packaged transport implementation.
- because `RuntimeProvider` treats the validated WebSocket as the authority for `coreStatus=online`, the frontend correctly remained stale/offline despite healthy HTTP state.
- RC3 inherited this packaged realtime defect because RC3 only changes recovery UI. It proved that updater controls can remain reachable while the core is degraded, but it is not a runtime-green or teardown-safe updater source.

## RC3 recovery-UX gate

- [ ] canonical version is `0.4.0-rc.3` across Python, npm/package-lock and Tauri/Cargo manifests.
- [ ] Settings renders desktop-shell recovery controls when `config=null` and the core is offline.
- [ ] `Check for updates` remains enabled independently of core availability.
- [ ] `Restart core` remains available from the installed desktop shell while the core is offline.
- [ ] autostart availability is derived from the Tauri plugin rather than core reachability.
- [ ] core-owned preference, Remote Access and Support Bundle actions remain unavailable or disabled while the core is offline.
- [ ] frontend regression tests cover the offline recovery surface.
- [ ] signed `v0.4.0-rc.3` release refreshes `update-rc/latest.json` to RC3.

## RC4 packaged realtime gate

- [ ] canonical version is `0.4.0-rc.4` across Python, npm/package-lock and Tauri/Cargo manifests.
- [ ] `websockets` is an explicit runtime dependency in both package metadata and Windows source requirements.
- [ ] PyInstaller deterministically collects the WebSocket runtime alongside Uvicorn.
- [ ] the sidecar entrypoint forces headless mode while preserving shell-supplied loopback host/port arguments.
- [ ] Windows packaging CI launches the actual `DS5ForgeCore.exe` and receives HTTP health through loopback.
- [ ] packaged-core smoke receives `101 Switching Protocols` for `/api/v1/ws` with `Origin: http://tauri.localhost`.
- [ ] the first packaged WebSocket frame is a version-1 `state.snapshot` event.
- [ ] Tauri Windows CI repeats the packaged-core smoke before bundling the sidecar.
- [ ] signed Windows release workflow repeats the packaged-core smoke before publication.
- [ ] signed `v0.4.0-rc.4` release refreshes `update-rc/latest.json` to RC4.

## RC2 lifecycle finding after packaged-core validation — 2026-09-15

A later inspection of the still-installed RC2 exposed a shutdown-safety defect that RC4 also inherits:

- the desktop shell process was no longer running, but two `ds5forge-core.exe` processes (PyInstaller wrapper + child) remained alive.
- TCP port `8765` was already closed, so the old supervisor would have considered the core stopped even though the executable process tree was still present.
- the updater calls the Tauri `stop_core` command before `downloadAndInstall`; returning success on port closure alone can let the installer attempt to replace a still-loaded `ds5forge-core.exe`.
- CI's packaged-core smoke did not reproduce this because Windows runners have no physical DualSense/audio runtime; the packaged core exits cleanly there. Real hardware evidence therefore remains authoritative for this lifecycle path.
- RC4 proves the packaged WebSocket runtime but is not accepted as a safe updater source until process-tree teardown is hardened.

## RC5 sidecar process-termination gate

- [ ] canonical version is `0.4.0-rc.5` across Python, npm/package-lock and Tauri/Cargo manifests.
- [ ] `CommandEvent::Terminated` is recorded per sidecar generation before stale-monitor checks.
- [ ] `stop_core` waits boundedly for the active sidecar process generation to terminate; loopback-port closure alone is insufficient.
- [ ] Windows forced fallback uses `taskkill /PID <pid> /T /F` with `CREATE_NO_WINDOW` to terminate the PyInstaller wrapper and descendants.
- [ ] updater/quit returns an explicit shutdown error if process-tree termination cannot be confirmed.
- [ ] `RunEvent::ExitRequested` prevents application exit when teardown fails, so tray Quit cannot intentionally leave the core orphaned.
- [ ] packaged-core Windows smoke tracks the launched `DS5ForgeCore.exe` PIDs and fails if any remain alive after lifecycle stop.
- [ ] forced fallback success is surfaced in lifecycle diagnostics rather than silently hidden.
- [ ] Windows native `cargo fmt`, `cargo check` and `cargo clippy -D warnings` pass.
- [ ] installed RC5 with a real wired DualSense proves Restart Core and tray Quit leave no `ds5forge-core.exe` process and no listener.
- [ ] only after that real RC5 teardown proof may RC5 be used as the source for an in-app updater E2E to a later RC.

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

## Updater end-to-end — source candidate must include RC5 teardown hardening

RC1/RC2 could not expose a reliable updater surface, RC3 fixed recovery UI, and RC4 fixed packaged realtime transport. Real RC2 lifecycle evidence then showed that RC2-RC4 can report `stop_core` success after the loopback API closes while the PyInstaller process tree is still alive. Therefore RC3 -> RC4 is no longer accepted as a safe updater proof.

The first valid updater E2E must start from an installed RC5 (or later) that has already passed real-hardware teardown validation, and target a newer signed RC. If RC5 passes lifecycle validation without further code changes, publish a minimal later RC solely to exercise the signed updater path from RC5.

- [ ] installed RC5 (or later teardown-safe source) detects the next RC through `update-rc`.
- [ ] detached signature is accepted.
- [ ] core is neutralized and the actual sidecar process tree terminates before updater installation starts.
- [ ] passive Windows update completes.
- [ ] updated app reports the target RC, starts the packaged core and reaches WebSocket `online` state.
- [ ] profiles/config/user data remain intact.
- [ ] invalid signature/update is rejected and current install remains usable.
- [ ] downgrade metadata is rejected.
- [ ] after stable `0.4.0` is published, an installed RC detects and can promote to stable.

## GO rule

`v0.4.0` stable is allowed only when CI, Windows lifecycle, physical USB, Remote Access and RC-to-RC updater evidence are green, with stabilization bugs closed or explicitly accepted. Until then report `RELEASE CANDIDATE — WINDOWS/HARDWARE VALIDATION PENDING`.
