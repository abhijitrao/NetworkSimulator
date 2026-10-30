# Development Plan

## Product decisions

- Windows 11, portable-first; do not require an installer or Windows service.
- Python TCP proxy engine with an HTML/JavaScript dashboard.
- No Toxiproxy dependency.
- Plain TCP and TLS passthrough are both first-class use cases.
- TLS stays end-to-end: no TLS termination, MITM CA, or weakened certificate checks.
- Multiple server profiles can be saved and activated simultaneously, each with its own listen address/port and upstream hostname/IP/port.
- Loopback-only management API; explicit listener binding on trusted network interfaces only.
- Never log transaction payloads, PAN, PIN blocks, track data, credentials, or arbitrary application bytes.

## Multiple configuration handling

A profile should include:
- Stable profile ID and display name.
- Upstream hostname/IP and port.
- Local bind address and listen port.
- Optional protocol label (TCP or TLS passthrough). TLS is still opaque byte forwarding.
- Enabled/disabled state.
- Default fault profile and per-direction fault settings.
- Connect timeout and operational notes.

The dashboard should support create, edit, duplicate, delete, import/export JSON, select active profile, start/stop individual proxies, and start/stop all valid profiles. Validate listener-port collisions before starting. Persist configuration atomically and keep profile ordering stable. Never silently overwrite profile IDs or active configurations.

## Fault injection semantics

Initial scenarios:
1. Normal forwarding.
2. Added latency and jitter independently per direction.
3. Pause forwarding in one direction (models an application response/read stall, not a server that never received bytes).
4. Upstream connect failure.
5. Graceful close and best-effort abort/reset on supported platforms.
6. Bandwidth throttling independently per direction.
7. Stream chunk fragmentation (changes read/write chunk sizes; not packet fragmentation).

Do not implement "packet loss" by dropping bytes from a TCP stream: that corrupts the stream and is not equivalent to IP packet loss. Document that real packet loss/retransmission, connect-SYN blackholes, Wi-Fi loss, and whole-device offline scenarios need a gateway/firewall or OS-level test environment.

## Milestones

### M1 — Repository scaffold and core relay
- Configuration schema and validation.
- Concurrent TCP listener per profile.
- Bidirectional byte-preserving relay.
- Graceful shutdown and connection lifecycle handling.
- Unit tests with local echo/upstream test servers.

### M2 — Fault injection (implemented; validate in field)
- Per-direction latency/jitter.
- Pause/resume forwarding.
- Bandwidth throttling.
- Best-effort active connection abort.
- Integration tests for live response pause/resume and latency.

### M3 — Dashboard and profile management (implemented; validate in field)
- Profile list and editor, duplicate/delete.
- Start/stop per profile and all profiles.
- Live fault controls and quick scenario presets.
- Runtime status, active connection counts and byte counters.
- JSON import/export with merge or replace.
- Management API restricted to localhost.
- Responsive dashboard with no external font/CDN dependency.

### M4 — TLS passthrough validation
- Local TLS test server and test certificate fixtures.
- Validate normal handshake, hostname mismatch, untrusted certificate, and pinning compatibility from a test client.
- Confirm proxy never terminates TLS and never records payloads.

### M5 — Portable Windows packaging
- Start script and portable runtime strategy.
- No installer or service registration.
- Friendly diagnostics for bind/firewall/port errors.
- Document that endpoint security / AppLocker policies must not be bypassed and may require IT approval.

### M6 — POS field validation
- Test LAN routing from POS Wi-Fi to laptop listener.
- Validate PAX/Verifone TCP and TLS test transactions.
- Record observed app timeouts/retries and distinguish proxy faults from corporate network policy.
