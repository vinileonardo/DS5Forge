# P0 validation record

This is the validation record for the P0 implementation and its independent
code-review fixes. It is not a product/release approval and it does not replace
the physical Windows + DualSense USB smoke checklist.

## Automated gates

| Gate | Command / evidence | Result |
| --- | --- | --- |
| Format | `ruff format --check source tests` | PASS: 52 files formatted |
| Lint | `ruff check source tests` | PASS |
| Static typing | `mypy source/dualsense_companion` | PASS: 37 source files |
| Unit/integration | `pytest -q` | PASS: 45 passed |
| Stdlib fallback | `PYTHONPATH=source python3 -m unittest discover -s tests` | PASS: 45 run, 6 API tests skipped when optional web deps are absent |
| Source/package syntax | `python3 -m compileall -q source tests` | PASS |
| Python wheel | `pip wheel --no-deps --no-build-isolation .` | PASS: `ds5forge-0.1.0-py3-none-any.whl` built with bundled JSON resources |
| Coverage review | `pytest --cov=dualsense_companion` | PASS: 65% overall; critical extracted logic has targeted regression coverage |
| API smoke | HTTP health/state/config/profiles/commands + strict validation | PASS: automated ASGI tests |
| WebSocket smoke | initial snapshot, state update, reconnect and rejected unapproved browser origin | PASS: automated ASGI tests |
| Lifecycle | connect/reconnect/shutdown, callback cleanup, startup ordering, high-frequency input cadence | PASS: fake-adapter tests |
| Haptics | DSP, failed output retry, live mapping config, structural reload, device-change cadence/error state | PASS |
| Touchpad/output safety | gesture semantics, reset/disable failure cleanup, best-effort release of held mouse buttons | PASS |
| Windows adapters | non-USB rejection, WASAPI device-change check and SendInput state tracking via fakes | PASS |
| Boundary audit | hardware imports confined to `platform/windows`; core has no platform implementation imports | PASS |
| Wireless audit | source scan | PASS: no Bluetooth/wireless implementation added |
| Silent exception audit | source scan | PASS: no operational `except ...: pass` |
| Windows PyInstaller | GitHub Windows CI uses Python 3.12 | PENDING locally: supported Windows Python 3.12 runtime is not installed on this host |

## Independent review fixes

The independent review found and corrected P0 blockers before technical GO,
including: restoring high-frequency touch input without flooding state events;
strict USB-only transport enforcement after `pydualsense` detection; deterministic
synthetic-input cleanup; loopback-only API binding; typed/strict HTTP contracts;
bundled-profile name protection; failed motor-output retry semantics; config
health recovery; race-safe health mutations; WebSocket origin/logging rules;
upstream microphone-toggle motor behavior; startup-feedback ordering; WASAPI
device-change detection/cadence; and full-package static checking.

## Runtime / packaging constraints

P0 is pinned to Python 3.12.x. `source/build.bat` now fails early with a clear
message when invoked through another Python version rather than installing build
dependencies into an unsupported runtime.

The local API may bind only to `127.0.0.1`, `::1` or `localhost` in P0. Remote
exposure is not part of this sprint.

## Hardware status

`HARDWARE VALIDATION PENDING`

A real Windows + wired DualSense run is still required to verify the physical
USB lifecycle, audio-driven rumble, touchpad/mouse behavior, GUI and frozen
PyInstaller executable. Do not convert this status to PASS without the dated
checklist/log evidence from `docs/D0_SMOKE_CHECKLIST.md`.

## Review disposition

**P0 independent code review: GO.**

This GO covers the code/architecture and automated validation surface only.
Hardware validation, release, merge and deployment remain separate gates.
