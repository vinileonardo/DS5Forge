# ADR P4 — Virtual Gamepad Provider

## Decision

Virtual/XInput remains unavailable in P4. No driver, HidHide/ViGEm-like
provider or virtual device is installed, downloaded or bundled automatically.

## Acceptance bar for a future provider

A provider must independently demonstrate all of the following on supported
Windows versions: sustainable maintenance, signed distribution and safe
installation/removal, reliable physical-input suppression, deterministic
disconnect/crash/update/uninstall teardown, least-privilege security, and an
explicit prevention of double input. A fake provider remains test infrastructure
only and is not production evidence.

Until every condition is met, Native remains default, Remap is explicit and a
Virtual request returns a structured unavailable error without changing the
previous mode.
