# DS5Forge P2 validation record

Status: `GO TECHNICAL` for automated and source-level evidence after independent
review. The candidate is `GO FOR PHYSICAL WINDOWS USB VALIDATION`. Physical
Windows + DualSense USB evidence remains `HARDWARE VALIDATION PENDING`; no
physical hardware/release GO is declared yet.

## Automated Linux/core

Run from the repository root in Python 3.12:

```text
./.venv/bin/ruff format --check source tests
./.venv/bin/ruff check source tests
./.venv/bin/mypy source/dualsense_companion
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q source tests
./.venv/bin/python -m build --wheel
```

Recorded result for this sprint:

- Ruff format/lint: PASS;
- mypy package: PASS;
- pytest: PASS, 79 tests (70 sprint tests, 6 round-2B regression tests and 3
  round-3 regression tests);
- compileall: PASS.
- wheel build: PASS via `python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir /tmp/ds5forge-wheel` (the virtualenv has no `build` module or pip entry point).

The optional `source/make_icon.py` utility is outside the package mypy gate
because this Linux environment does not install Pillow. A full `mypy source`
run therefore reports the unrelated missing `PIL` stub; the required
`source/dualsense_companion` gate is green.

## Frontend

Run from `frontend/` after a clean `npm ci`:

```text
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
npm run e2e
npm audit --omit=dev
```

The frontend tests cover strict telemetry/event contracts, unknown-event
compatibility, input/stale visualizers, capability notices, output forms,
pending locks and profile import/export behavior. Playwright remains a mocked
local-core boundary test; it is not authenticated backend or physical-device
evidence.

Recorded result for this sprint: `npm ci` PASS with 0 audit vulnerabilities;
Prettier, ESLint, TypeScript, Vitest (6 files / 21 tests), Vite build and
Playwright (9 tests) PASS. `npm audit --omit=dev` PASS with 0 vulnerabilities.

Independent review round 2B added component/runtime regression tests for the
realtime stale trust boundary and for draft preservation in Haptics, Touchpad
and Settings, plus capability-count and dialog-wording coverage. Re-run from the
existing install: Prettier `format:check`, ESLint, TypeScript, Vitest
(10 files / 33 tests), Vite build, Playwright (9 tests) and `npm audit` PASS
with 0 vulnerabilities. Python gates were not re-run because this environment
blocks the virtualenv commands; no Python source was modified by the review.

Final independent review round 3 added a `ProfilesPage` regression test proving
that a profile apply which the runtime cannot fully honor surfaces the returned
`unsupported_sections` instead of only reporting success. Full round-3 re-run
from a clean `npm ci`: Prettier `format:check`, ESLint, TypeScript, Vitest
(11 files / 35 tests), Vite build, Playwright (9 tests) and `npm audit
--omit=dev` PASS with 0 vulnerabilities. Python Ruff format/check, mypy,
pytest (79 tests) and compileall were also re-run green after the round-3
facade changes.

## Windows build

The native Tauri shell and the PyInstaller path require Windows-native
verification. The shell must retain `core:default`, the narrow loopback CSP and
no process/sidecar/installer/updater/tray/autostart permissions. Run the
existing Windows CI/build commands on a Windows runner and record the exact
Python 3.12, Node, Rust/MSVC and WebView2 versions.

Static Tauri JSON/CSP/permission assertions PASS and `tauri info` confirmed
the intended narrow configuration. Cargo format/build could not run because
this environment has no Rust/Cargo and no `webkit2gtk-4.1`; Windows-native
Tauri build evidence remains `HARDWARE VALIDATION PENDING`.

## Physical wired USB

Complete `docs/D0_SMOKE_CHECKLIST.md` with a real DualSense connected by USB:

- controller connect/read/reconnect and neutralization;
- lightbar apply/reset when the adapter reports support;
- trigger preview timeout/cancel/disconnect/shutdown reset;
- bounded haptics test and audio-rumble coordination;
- touch points, gestures and synthetic mouse release;
- schema-v2 profile apply/import/export and unsupported-capability messaging.

No Bluetooth, pairing, dongle or wireless test is in scope.

Status: `HARDWARE VALIDATION PENDING` — no physical Windows evidence was
available in this environment.

## Known limitations and boundaries

- `pydualsense` is an optional Windows dependency; runtime capability detection
  reflects the installed adapter/library surface and may disable optional lab
  controls until physical verification confirms the mapping.
- Stick calibration/deadzone is DS5Forge visualization/profile metadata only;
  it does not alter native game input.
- Applying a legacy/bundled rumble-only profile now performs a full schema-v2
  apply: rumble values are preserved, while the migrated lightbar, trigger,
  stick and touchpad sections use neutral/default values. This is intentional
  full-profile behavior, but it is a change from the P0 rumble-only apply and is
  called out for reviewers.
- Failed lab output writes neutralize the touched hardware and align the
  authoritative snapshot with that neutral state; the HTTP error is still
  surfaced and the profile/lightbar/trigger response reports unsupported
  sections explicitly.
- The physical meaning of the lightbar brightness/pulse enums and trigger force
  slots is mapped from the published adapter surface and remains unverified
  until physical Windows USB evidence exists.
- A passing Linux adapter fake, frontend fixture or Playwright flow does not
  prove Windows HID, WASAPI, lightbar, adaptive-trigger or packaged-shell
  behavior.
- No final GO is declared until independent review and physical USB evidence
  are complete.
