# DS5Forge Agent Instructions

## Mission

Evolve DS5Forge from the `Casliyan/DS5companion` baseline into a production-quality Windows DualSense companion without throwing away working behavior unnecessarily.

## Non-negotiable scope

P0–P4 are **USB/wired only**.

Do not add or spend implementation time on:
- Bluetooth support;
- wireless transports;
- dongles/adapters;
- wireless pairing;
- wireless audio/haptics tuning.

If existing upstream code happens to contain generic support paths, do not expand them unless needed to keep USB behavior working.

## Architecture rules

1. The local controller core is the authority for hardware state.
2. UI code must not access `pydualsense`, WASAPI objects or Windows HID APIs directly.
3. Separate domain/state contracts from Windows-specific infrastructure.
4. Expose commands/config through a versioned local HTTP API.
5. Expose realtime state/events through WebSocket.
6. Prefer immutable/snapshot-style state exchange across thread/task boundaries.
7. Every hardware-dependent feature must expose capability/availability state.
8. Reconnect, shutdown and teardown must be deterministic.
9. Native DualSense behavior is the default. Compatibility/emulation layers must be opt-in.
10. Do not silently swallow operational exceptions. Convert expected failures into typed/structured errors and log unexpected ones.

## Upstream preservation

- Preserve the MIT license and upstream copyright notice.
- Keep attribution in `NOTICE.md`.
- Do not remove working behavior merely to make a refactor cleaner.
- Before replacing an upstream behavior, add/retain a regression test or an explicit smoke-test item covering it.

## Development style

- Work in large, coherent sprint blocks.
- Avoid speculative abstractions with no P0–P4 consumer.
- Prefer clear boundaries over framework-heavy architecture.
- Keep platform-specific code under a Windows/platform boundary.
- Use typed models/contracts at API boundaries.
- Add tests with each extracted domain behavior.
- Avoid giant files and mutable god objects.
- Do not introduce a driver dependency without an ADR explaining why it is necessary and how it is installed/removed safely.

## Safety / controller behavior

- On disconnect, crash or shutdown, actively return motors/triggers/virtual input to a neutral state where possible.
- Never leave synthesized keyboard/mouse/controller buttons logically held after teardown.
- Preview/test effects must have a timeout or explicit stop path.
- Invalid profiles/config values must not be sent directly to hardware.
- Any future virtual-controller mode must prevent double input and provide deterministic cleanup.

## Verification expectations

At minimum for every sprint:
- formatter/lint pass;
- type/static checks where applicable;
- unit tests pass;
- build/package checks for touched surfaces;
- Windows USB smoke checklist updated when behavior changes;
- no new Bluetooth/wireless implementation;
- no regression in baseline haptics/touchpad unless explicitly accepted.

## Source of truth

Read `docs/D0_BASELINE_AND_ROADMAP.md` before implementing sprint work.

If a sprint Execution Pack conflicts with this file, stop and surface the conflict rather than guessing.
