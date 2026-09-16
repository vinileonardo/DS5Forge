# P4 Validation Record

Status is evidence-based; an automated Linux pass does not substitute for
Windows or physical DualSense proof.

## Source and automated gates

Commands for this sprint:

```text
python3 scripts/validate_versions.py
python3 -m compileall -q source scripts tests
python3 -m pytest
cd frontend && npm ci && npm run format:check && npm run lint && npm run typecheck && npm test && npm run build
```

The final run must record the exact result here. New P4 tests cover lifecycle
readiness/timeouts/restart bounds, session pairing/expiration/revocation,
remote OFF, origin/cookie rules, diagnostics, bundle sanitization/path bounds,
tunnel absence/configuration, update metadata and downgrade rejection.

## Recorded automated run — 2026-09-15

- `python3 scripts/validate_versions.py` and `python3 -m compileall -q source scripts tests`: PASS.
- Ruff format/check and mypy: PASS.
- Python pytest: **120 passed**.
- Python wheel: `ds5forge-0.4.0-py3-none-any.whl` built successfully.
- Frontend Prettier, ESLint, TypeScript, Vitest (**41 passed**), Vite build and production npm audit: PASS.
- Playwright E2E: **11 passed**.
- Initial handoff did not yet prove the Tauri Rust/Windows gates; the independent final pass below supersedes that native-toolchain gap.

## Security and boundary checks

- [x] API bind remains `127.0.0.1`/other loopback only.
- [x] No arbitrary shell command, filesystem permission, HTTP wildcard or
  global Tauri permission exists.
- [x] Sidecar args are fixed to headless loopback execution.
- [x] No token/cookie/credential/private key appears in logs, exceptions,
  telemetry or Support Bundle content.
- [x] Remote HTTP and WebSocket both require the same authenticated session;
  origin is exact HTTPS and explicitly registered.
- [x] Tunnel starts only after an active remote session and configuration is valid.
- [x] Wired-only audit finds no new implementation path for Bluetooth/wireless.

## Windows evidence

`WINDOWS RUNTIME VALIDATION PENDING` until a Windows 10/11 runtime records:

- clean per-user NSIS install, reinstall and upgrade;
- sidecar launch/readiness, bounded restart and no orphan process;
- tray, single-instance focus/restore and reversible autostart;
- signed updater passive progress, failed-update recovery and rollback procedure;
- uninstall preserving user data and leaving no external listener;
- Remote OFF with no tunnel/session/listener.

## USB evidence

`HARDWARE VALIDATION PENDING` until the wired checklist records real
DualSense connect/reconnect, haptics, touchpad, trigger/motor neutralization,
profile/game teardown and update/restart/uninstall cleanup.

## Independent review addendum (block 1-2)

An independent review of the P4 delta against `14ddf16` on Linux/source fixed
the following before handoff:

- the HTTP/WebSocket middleware no longer fails open for origin-less requests
  whose Host is not loopback while remote access is enabled; such requests must
  authenticate;
- `/lifecycle/stop` (quit, restart, update, uninstall) now stops the outbound
  cloudflared child and asks the sidecar to terminate itself, and the shell
  waits for the API port to close before falling back to `kill`;
- a generation guard prevents a stale child monitor from taking or restarting a
  replaced sidecar, and a coordinated stop during crash backoff no longer
  resurrects the core;
- Support Bundles redact free-text machine paths (Windows drive/UNC and common
  POSIX directories), not only path-shaped keys;
- `scripts/validate_versions.py` is mypy-clean and fails closed on a malformed
  manifest.

Re-run source gates: pytest **125 passed**; `ruff check`/`ruff format --check`
PASS; `mypy scripts source/dualsense_companion` PASS (64 files); `compileall`
PASS; `validate_versions.py` OK `0.4.0`. Frontend: Prettier, ESLint, `tsc`,
Vitest **41 passed**, Vite build and production `npm audit` PASS.

## Independent review final pass (block 3)

The stale Rust lock/toolchain gap was closed with the native Windows Rust toolchain
(`cargo 1.98.1` / `rustc 1.98.1`) invoked from the Windows host. Native compilation
could not run before, so it exposed two source defects the Linux/source gates cannot:

1. (Major, fixed) the Tauri crate used `tauri::generate_context!()` without declaring
   `serde_json` directly. `serde_json` was added, `Cargo.lock` was regenerated, and the
   lock now records `ds5forge 0.4.0`, `serde_json`, and the required Tauri plugins.
2. (Critical, fixed) `plugins.updater` was configured with `windows.installMode` but no
   `pubkey`. `tauri-plugin-updater` declares `pubkey: String` with no serde default, so
   `App::build` fails plugin initialization and the shell's `.expect(...)` would panic on
   every launch. A clearly unset placeholder (`"pubkey": ""`, `"endpoints": []`) keeps
   plugin initialization deserializable for normal builds; the signed release overlay in
   `scripts/build_installer.py` still injects the real `TAURI_SIGNING_PUBLIC_KEY` and
   endpoint. Clippy also closed `manual_div_ceil` and `needless_borrow` warnings required
   by the CI `-D warnings` gate.

Four static `TestTauriReleaseContract` tests now guard the manifest dependency, the lockfile
plugin graph, the deserializable updater config, and the minimal capability scope so
these defects cannot silently return. Update metadata comparison was also hardened to
honor SemVer prerelease precedence (numeric-identifier ordering and build-metadata
equality) and is covered by `test_update_uses_semver_prerelease_precedence`.

Native Windows Rust proof after those fixes:

- `cargo fmt --all -- --check`: PASS.
- `cargo check --all-targets --all-features --config build.incremental=false`: PASS.
- `cargo clippy --all-targets --all-features --config build.incremental=false -- -D warnings`: PASS.
- A temporary sidecar placeholder was used only to satisfy Tauri's `externalBin`
  existence check during compile validation and was removed immediately afterward;
  no generated `frontend/src-tauri/binaries/` directory remains in the working tree.
- `--config build.incremental=false` is only needed because this Linux checkout is
  compiled over the WSL UNC path; a native Windows checkout does not require it.

### Proof boundary

Native Windows Rust compilation proves the Tauri crate and configuration compile and
that the manifest, lockfile and plugin graph resolve. It does **not** prove runtime
behavior.

Proven by native Windows Rust compilation: `cargo fmt`/`check`/`clippy`, the plugin
dependency graph, `tauri::generate_context!` expansion, and updater plugin config
deserialization (now guarded by static tests).

Still requiring Windows runtime (NSIS/Tauri execution): clean per-user install,
reinstall and upgrade, packaged sidecar launch/orphan cleanup, tray, single-instance,
autostart, signed updater end-to-end, and Remote OFF leaving no listener.

Still requiring physical hardware: wired DualSense connect/reconnect, haptics, touchpad,
trigger/motor neutralization and profile/game teardown.

Final regression gates on the resulting source state:

- `validate_versions.py`: PASS, version `0.4.0`.
- Ruff format/check: PASS (**85 files**).
- mypy `source/dualsense_companion scripts`: PASS (**63 source files**).
- Python `compileall`: PASS.
- Python pytest: **129 passed** (adds 4 Tauri manifest/lock/updater/capability contract tests).
- Frontend Prettier, ESLint and TypeScript: PASS.
- Vitest: **41 passed** across **12 files**.
- Vite production build: PASS.
- `npm audit --omit=dev`: PASS, **0 vulnerabilities**.
- Playwright E2E: **11 passed**.
- `git diff --check -- .`: PASS.
- Wired-only implementation audit: PASS; no Bluetooth/wireless/BLE implementation
  path was introduced.
- Tauri capability boundary remains explicit: fixed sidecar only, fixed headless
  loopback args, no arbitrary shell-open permission, and no filesystem/HTTP wildcard.
- `docs/P2_REVIEW_SCOPE.json` and `docs/P2_REVIEW_SCOPE_V2.json` remained untouched
  during the P4 review.

With those two source defects fixed, no unresolved source Critical/Major remains. The
remaining evidence is runtime/hardware evidence only: clean NSIS
install/reinstall/upgrade/uninstall, real packaged sidecar launch/orphan cleanup,
tray/single-instance/autostart behavior, signed updater end-to-end behavior, and
physical wired DualSense validation remain `WINDOWS RUNTIME VALIDATION PENDING` /
`HARDWARE VALIDATION PENDING` as listed above.
