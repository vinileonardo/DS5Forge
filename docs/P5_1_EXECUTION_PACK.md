# P5.1 Execution Pack — Windows Live Validation and Input Isolation

Branch: `fix/p5.1-windows-live-validation`
Baseline: `f882ce4b37e59c2d4cecc22f6dd2bb0e950d40b6`
Scope: Windows + DualSense USB/wired only. No Bluetooth/wireless implementation.

## Objective

Close the gap between the P5 source-level implementation and a real Windows/USB product flow. P5.1 must make game lifecycle tracking, anti-double-input, hardware validation and live development observable and operational without weakening Native as the default.

## Non-negotiable outcomes

1. **Game lifecycle is process-driven, not foreground-driven.**
   - A registered game remains active while its configured `.exe` is alive, even after Alt+Tab.
   - Foreground is context and priority when multiple eligible registered games are running.
   - Closing the process triggers the configured exit policy.
   - Exact-path rules remain exact when a full path is available/configured.

2. **Games UX is resilient.**
   - No horizontal overflow/cut text at supported desktop/mobile widths.
   - Long executable paths, rule reasons and provider diagnostics wrap safely.
   - Action rows wrap rather than push content outside cards.
   - Running-process state and foreground state are described separately.

3. **pt-BR is natural and complete on P5.1 surfaces.**
   - No raw booleans (`true`/`false`) or English state labels in the Games primary path.
   - Backend diagnostic/reason strings shown to users are localized or converted to structured presentation copy.
   - Terms such as provider/provenance are translated/explained where surfaced.

4. **Live Dev Bridge exists.**
   - Provide a documented command/scriptable path to inspect Windows processes, the local HTTP API, WebSocket-relevant health/runtime state and installed DS5Forge processes from the WSL checkout.
   - The bridge must be diagnostic/development-only and must not expose an external listener by default.

5. **Anti-double-input is operational on Windows with HidHide when available.**
   - The user can request a double-input fix from DS5Forge.
   - For Remap, physical DualSense input can be isolated through an installed HidHide driver while DS5Forge remains allowlisted and continues reading the controller.
   - HidHide state is probed and verified after changes.
   - The currently connected DualSense USB device instance is discovered dynamically; stale device IDs are not trusted.
   - Enable is transactional: allowlist DS5Forge -> hide current device -> enable cloak -> verify.
   - Disable/rollback is deterministic and restores visibility when DS5Forge owns the isolation session.
   - Full virtual DualSense/HIDMaestro remains a separate capability and must not be faked if absent.
   - No driver is silently downloaded or installed.

6. **Physical Windows validation is executed and recorded.**
   - Lightbar enabled/off, RGB intensity and pulse.
   - Player LEDs remain independent of RGB lightbar state.
   - Adaptive trigger preview/reactive path/reset.
   - Input isolation / double-input diagnostics with the physical controller.
   - Game process lifecycle across foreground/background/exit.
   - API/core packaged lifecycle with no duplicate sidecar after restart/quit.

## Architecture constraints

- Python core remains the hardware authority.
- UI never calls HidHide, pydualsense or Win32 APIs directly.
- Windows-only HidHide/process code lives under `source/dualsense_companion/platform/windows/`.
- All operations have typed status and structured errors.
- Native mode stays default; isolation is explicit and reversible.
- Existing P0–P5 regression coverage and upstream attribution are preserved.

## Validation gates

Python/source:

```text
./.venv/bin/ruff check source tests
./.venv/bin/ruff format --check source tests
./.venv/bin/mypy source
./.venv/bin/python -m compileall -q source tests
./.venv/bin/pytest -q
python3 scripts/validate_versions.py --expected 0.4.0-rc.8
git diff --check
```

Frontend:

```text
cd frontend
npm run format:check
npm run lint
npm run typecheck
npm test -- --run
npm run build
npm run e2e
```

Windows native/package:

```text
cd frontend/src-tauri
cargo fmt --check
cargo check --all-targets --all-features
cargo clippy --all-targets --all-features -- -D warnings
```

Final handoff must separate automated evidence from real Windows/hardware evidence. Do not mark a hardware behavior PASS without observing it on the connected DualSense.
