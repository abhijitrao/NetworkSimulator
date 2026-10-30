# M1 — Core TCP Proxy

## Implemented

- Standard-library-only TCP listener and upstream connector.
- Bidirectional byte-preserving stream relay.
- TLS passthrough as opaque TCP bytes; no TLS termination or certificate handling in the proxy.
- Concurrent client handlers and independent proxy runtimes.
- Multiple profiles with independent listener ports and upstream endpoints.
- Atomic JSON profile persistence and duplicate ID / listener collision validation.
- Per-profile start/stop and stop-all lifecycle management.
- Active connection metadata and byte counters (payload bytes are never logged).
- Unit/integration tests for echo forwarding, concurrent clients, profile persistence, import merge and port collisions.
- CLI runner: `python run_proxy.py --config config/profiles.example.json`.

## Run locally

1. Install Python 3.10+ using an approved/portable runtime.
2. Copy `config/profiles.example.json` to a local file, for example `config/profiles.local.json`.
3. Set the upstream host/port and a unique local listen port for each profile.
4. Set `enabled` to `true` only for profiles you want to start.
5. Run `python run_proxy.py --config config/profiles.local.json`.
6. Press Ctrl+C to stop all profiles.
7. Run tests with `python -m unittest discover -s tests -v`.

## Important

- Bind to `127.0.0.1` for local-only testing. To accept POS traffic, choose the laptop's reachable LAN IPv4 address or `0.0.0.0` only on a trusted network and only with required IT approval.
- A listener can start without admin rights in many Windows configurations, but Windows Firewall or corporate endpoint policy may block inbound LAN connections.
- The profile's `transport_label` is descriptive. The proxy always forwards raw TCP bytes; TLS negotiation remains between the POS app and upstream server.
- For TLS hostname validation, POS code must connect the TCP transport to the laptop proxy but layer TLS using the original upstream hostname as the peer identity. Keep normal trust managers, hostname verification and pinning enabled.
- This milestone is the core engine only; the dashboard and fault-injection controls are subsequent milestones.
