# ADR P4 — Update Strategy

## Decision

Use the official Tauri updater with HTTPS endpoints and detached signatures.
Normal builds produce a usable NSIS installer without a signing key and do not
create updater artifacts. Tagged release builds require
`TAURI_SIGNING_PRIVATE_KEY` and a public key supplied only through CI secrets;
no key is versioned. A signed tag build publishes a versioned GitHub Release
with the NSIS installer, detached signature, checksums and updater metadata.
Stable builds use GitHub's `releases/latest` metadata endpoint. Prerelease
builds use a fixed `update-rc` channel whose `latest.json` asset is refreshed by
CI; the stable release refreshes that same channel once so installed RCs can
promote to the final version.

Windows uses passive installer mode with progress. UI states are checking,
available, downloading, installed/restart-required, unavailable and failed.
An update error leaves the current installation running.

## Rollback

Rollback is documented as reinstalling the last known-good signed NSIS/update
artifact. The updater must reject downgrades in metadata validation unless an
explicit future recovery command establishes a signed rollback policy. Core
teardown runs before update/restart so motors, triggers, previews, synthetic
outputs and automation are released.
