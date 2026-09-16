# ADR P5 — Capability-gated Exclusive input provider

## Status

Proposed for P5. The implementation is present behind an explicit capability
gate; it is not a claim that a production Windows provider is installed or
validated.

## Context

Exclusive input has two safety-critical halves:

1. a virtual DualSense output-report source that mirrors the complete wired
   controller state; and
2. session-scoped suppression of the physical controller.

Starting only one half creates duplicate input or a missing controller. A
provider is therefore not operational merely because its executable or API is
available. Provenance, integrity, signature, output-report behavior, session
ownership and Windows validation must all be demonstrated.

The first integration design is HIDMaestro for the virtual DualSense and
HidHide for physical suppression. HIDMaestro documents virtual controllers,
output-report/force-feedback handling and orphan recovery in its
[official repository](https://github.com/hifihedgehog/HIDMaestro). HidHide
documents process-associated session blacklists and developer integration in
its [Developer Guide](https://github.com/nefarius/HidHide/blob/master/DEVELOPER.md).
Those references inform the adapter boundary; they do not constitute DS5Forge
installation, signature or Windows runtime evidence.

## Decision

Exclusive is implemented as a platform-neutral coordinator with Windows-only
provider adapters:

- `VirtualControllerProvider`/`VirtualOutputReportSource` owns the virtual
  report sink;
- `PhysicalInputSuppressionProvider` owns session suppression;
- `ExclusiveCoordinator` owns ordering, generation, ownership token,
  heartbeat/watchdog, mirroring, stale recovery and rollback;
- clients consume immutable capability/status/diagnostic models and never
  access HID APIs or provider objects directly.

The transaction is:

```text
probe -> verify capability/provenance -> start virtual -> suppress physical
     -> heartbeat + mirror state -> unsuppress physical -> close virtual
```

If either start step fails, the coordinator tears down every step that did
start and leaves `physical_input_visible=true`, `virtual_input_active=false`
and `double_input_risk=true`. A failed mirror, missed heartbeat, reconnect,
shutdown, updater stop or uninstall path also disables the session and attempts
neutral cleanup.

The helper boundary is a fixed, versioned JSON-lines sidecar. It uses a fixed
executable basename, pinned SHA-256, `shell=False`, parent PID, ownership token,
generation and heartbeat. DS5Forge does not download, install, discover or
execute an arbitrary provider command. There is no `pythonnet` boundary and no
ViGEmBus dependency. Recovery is attempted at startup before a new session;
the helper remains responsible for provider-specific stale cleanup.

Exclusive is OFF by default. Until every gate is true, the capability is
non-operational and `/diagnostics/duplicate-input` reports risk. A visible
provider without verified suppression is a warning, not a success state.

## Capability gates

All of the following are required:

| Gate | Required evidence |
| --- | --- |
| Provider availability/installation | fixed helper/provider is present and responds to the versioned protocol |
| Output reports | real DualSense report submission is demonstrated, not inferred from a symbol name |
| Suppression | session-scoped physical suppression is active and recoverable |
| Provenance | expected provider/helper identity and version are recorded |
| Integrity | the fixed helper hash matches the pinned release value |
| Signature | Authenticode/signing verification succeeds |
| Windows validation | a real Windows USB run proves enable, mirror, disable, crash and recovery |

The source implementation and deterministic fakes can exercise the state
machine, but they cannot satisfy the final Windows gates. Anti-cheat visibility,
driver policy and provider distribution constraints remain product risks and
must be assessed with the intended game/provider combination.

## Consequences

Native DualSense remains the default. Remapping remains a separate mode with
its own duplicate-input warning. Exclusive, physical suppression, remote
access, reactive trigger generation and any provider installation are disabled
unless explicitly enabled and proven. The final handoff must retain the label
`WINDOWS/HARDWARE VALIDATION PENDING` until the evidence above exists.
