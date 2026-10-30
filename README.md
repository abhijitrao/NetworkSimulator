# POS Network Simulator

A portable-first Windows desktop tool for testing TCP and TLS passthrough connectivity from physical Android POS terminals through a configurable local TCP proxy.

## Goals

- Forward plain TCP and TLS-encrypted TCP streams without terminating TLS.
- Preserve the original TLS hostname/SNI by configuring the Android client to connect to the proxy transport while retaining the original peer identity.
- Inject controlled delay, jitter, response stalls, bandwidth limits, and connection failures.
- Manage multiple independent upstream profiles (host, port, protocol label, listener port, notes, and scenario defaults).
- Keep management APIs bound to loopback; expose only explicitly enabled proxy listeners on trusted LAN interfaces.
- Avoid an installer and Windows service; target a user-writable portable folder.

## Configuration model

Each profile represents one upstream endpoint and one local listener. Multiple profiles can be active concurrently, subject to available ports and OS/network policy. Profiles are stored locally in JSON and are not automatically uploaded.

## TLS safety

The proxy is a byte-stream relay and does not inspect or decrypt application payloads. Certificate-chain validation, hostname verification, SNI, and certificate pinning remain the responsibility of the POS TLS client and the upstream server. The Android client must preserve the original TLS peer hostname when layering TLS over a socket connected to the proxy. Never disable certificate validation to make proxying work.

## Network limitations

A user-space TCP relay can delay or stop forwarding stream data and close connections. It cannot faithfully emulate IP-layer packet loss, Wi-Fi disassociation, or loss of internet access for the entire device. Those scenarios require an approved network gateway, firewall, or OS-level network test setup.

## Development status

Initial repository scaffold. See `docs/DEVELOPMENT_PLAN.md` for milestones and design constraints.
