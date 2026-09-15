# ADR P4 — Remote Access

## Decision

Remote Access is opt-in. The local API continues to bind only to loopback.
Pairing starts in the local UI and creates a one-use code with a short TTL.
Completion requires an exact HTTPS origin and creates a revocable session. The
raw secret is returned once as a `Secure; HttpOnly; SameSite=Strict` cookie;
only a SHA-256 digest/reference is persisted.

Every remote browser HTTP and WebSocket request must present the same cookie
and exact registered Origin. Origin-less non-browser requests are recognized
only when their Host matches that registered origin's netloc, and still need
the same cookie. Expiration, revocation, disable and reconnect are explicit
states. Disable clears sessions and stops the tunnel. Tokens are forbidden in
query strings, logs, events, telemetry and support bundles.

`cloudflared` is an explicit external dependency. DS5Forge detects it and
validates a user-selected YAML config but never downloads, installs, updates or
exports a raw token. It starts only when remote access has an active session and
uses a non-shell outbound-only process boundary.

## Rejected alternatives

An unauthenticated public loopback proxy, query-string token, wildcard origin,
inbound Windows listener and silently managed cloudflared binary all violate
the local-authority or credential boundary.
