# POS Network Simulator

A portable-first Windows tool for testing plain TCP and TLS passthrough connectivity from physical Android POS terminals through a configurable local TCP proxy.

## Current capabilities

- Concurrent bidirectional TCP relay; TLS is forwarded as opaque bytes without TLS termination.
- Multiple independent endpoint profiles with separate upstream endpoints and listener ports.
- Live directional latency, jitter, bandwidth throttling and response/request forwarding pause.
- Best-effort active connection abort.
- Local HTML dashboard for profile CRUD, duplicate, start/stop, start-all/stop-all, connection status and byte counters.
- JSON profile import/export with merge or replace mode.
- Local-only management API; no payment/application payload logging.

## Quick start (Windows)

1. Use an IT-approved Python 3.10+ runtime available to your Windows user.
2. Install the dashboard dependency in your permitted user environment: `python -m pip install --user -r requirements.txt`.
3. Run `start.bat`.
4. Open `http://127.0.0.1:5050` if the browser does not open automatically.
5. Add an endpoint profile and start it. Use a unique listener port for every profile.

For local laptop-only testing, bind a proxy profile to `127.0.0.1`. To accept a physical POS device, select the laptop's reachable LAN IPv4 address or `0.0.0.0` on a trusted network. Office VLAN routing, Wi-Fi client isolation, Windows Firewall and endpoint security may require IT approval. Do not bypass corporate controls.

## Multiple configurations

Profiles are stored locally at `data/profiles.json` and are not committed by default. Example profiles are in `config/profiles.example.json`. Each profile owns an upstream host/port, bind address/listen port, TCP/TLS label and independent fault settings. Import can merge with existing profiles or explicitly replace them.

## TLS and certificate validation

The proxy does not decrypt TLS. Certificate-chain validation, hostname verification, SNI and certificate pinning remain end-to-end between the POS TLS client and actual upstream server. When the POS connects its raw TCP socket to the laptop proxy, layer TLS using the original server hostname as the peer identity. Never disable certificate validation or install a test root CA on production POS devices.

## Fault semantics and limitations

- Latency/jitter and bandwidth are applied to stream chunks in user space; this is not precise packet-level emulation.
- Pause POS-to-server forwarding to stall requests; pause server-to-POS forwarding to simulate a delayed/no response while the POS read timeout expires.
- Abort closes active sockets; exact RST behavior and error codes are OS/timing dependent.
- Dropping bytes from a TCP stream is not packet-loss simulation. Real packet loss/retransmission, SYN blackholes, Wi-Fi disassociation and whole-device internet outage require an approved gateway/firewall or OS-level test setup.

## Development

- [Development plan](docs/DEVELOPMENT_PLAN.md)
- [Configuration schema](docs/CONFIGURATION_SCHEMA.md)
- [M1 core proxy](docs/M1_CORE_PROXY.md)
- [M2/M3 dashboard and fault injection](docs/M2_M3_FAULTS_DASHBOARD.md)

Run tests: `python -m unittest discover -s tests -v`.
