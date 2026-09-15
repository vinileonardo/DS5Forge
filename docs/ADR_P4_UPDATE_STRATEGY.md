# ADR P4 — Update Strategy

## Decision

Use the official Tauri updater with HTTPS endpoints and detached signatures.
Normal builds produce a usable NSIS installer without a signing key and do not
create updater artifacts. Tagged release builds require
`TAURI_SIGNING_PRIVATE_KEY` and a public key supplied only through CI secrets;
no key is versioned. The release workflow builds artifacts/checksums/metadata
but never publishes a GitHub Release.

Windows uses passive installer mode with progress. UI states are checking,
available, downloading, installed/restart-required, unavailable and failed.
An update error leaves the current installation running.

## Rollback

Rollback is documented as reinstalling the last known-good signed NSIS/update
artifact. The updater must reject downgrades in metadata validation unless an
explicit future recovery command establishes a signed rollback policy. Core
teardown runs before update/restart so motors, triggers, previews, synthetic
outputs and automation are released.
