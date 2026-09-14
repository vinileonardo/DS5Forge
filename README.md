# DS5Forge

DS5Forge is a Windows-first DualSense companion focused on making the controller feel first-class on PC while preserving native game support whenever possible.

The project starts from the open-source [`Casliyan/DS5companion`](https://github.com/Casliyan/DS5companion) baseline and evolves it into a more robust architecture with a local controller core, real-time API/WebSocket layer, modern PC-first UI, desktop packaging, profiles, diagnostics, deeper DualSense controls and game-aware automation.

## Current scope

**USB / wired only for P0–P4.** Bluetooth and other wireless transports are intentionally deferred.

## Product direction

- excellent Windows desktop experience;
- browser-accessible UI backed by the same local core;
- responsive mobile control surface when accessing the local instance remotely;
- real-time state over WebSockets;
- optional secure remote access through Cloudflare Tunnel;
- preserve native DualSense behavior by default;
- compatibility/emulation features must be explicit opt-in modes;
- strong diagnostics, reconnect behavior and safe teardown.

## Baseline capabilities inherited from upstream

- DualSense USB connection through `pydualsense`;
- Windows WASAPI loopback capture;
- audio-driven rumble;
- touchpad mouse control and basic gestures;
- profiles/configuration;
- Windows desktop GUI and PyInstaller build flow.

The legacy baseline is being preserved first; architectural changes begin only after D0 is complete.

## Roadmap

See [`docs/D0_BASELINE_AND_ROADMAP.md`](docs/D0_BASELINE_AND_ROADMAP.md).

The planned delivery is split into five large sprints:

- **P0** — Foundation / Core Authority
- **P1** — PC-first UX / Web + Desktop
- **P2** — Controller Lab / DualSense Depth
- **P3** — Compatibility / Games / Automation
- **P4** — Productization / Release / Remote Control

## Upstream and license

DS5Forge is derived from `Casliyan/DS5companion`, originally released under the MIT License.

Original copyright notice and license terms must be preserved in all substantial portions derived from the upstream project. See `LICENSE` and `NOTICE.md`.
