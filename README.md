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

## Quick start (portable Windows EXE)

1. Download the latest `NetworkSimulator-Windows-x64` artifact from the repository's **Actions → Build portable Windows EXE** workflow.
2. Extract the downloaded artifact ZIP to a normal user-writable folder, for example `D:\\Tools\\NetworkSimulator`.
3. Double-click `NetworkSimulator.exe`. No separate Python or Flask installation is needed.
4. The dashboard opens at `http://127.0.0.1:5050`. If it does not, open that address manually.
5. Add an endpoint profile and start it. Use a unique listener port for every profile.

The EXE stores profiles in a `data` folder beside the EXE. Keep the EXE in a folder where your Windows user can create and modify files. This is a portable, unsigned build; Windows SmartScreen or company endpoint policy may still show a warning or block execution. Do not bypass company security controls—ask IT to approve the executable if needed.

## Development run (Python)

1. Use an IT-approved Python 3.10+ runtime available to your Windows user.
2. Install the dashboard dependency in your permitted user environment: `python -m pip install --user -r requirements.txt`.
3. Run `start.bat`.

To build locally on Windows, install the packages in `requirements-build.txt` and run the PyInstaller command from `.github/workflows/build-windows-exe.yml`.

## Physical POS connectivity and mobile hotspot

For laptop-only testing, bind a proxy profile to `127.0.0.1`. To accept a physical POS device, connect the laptop and POS to the same mobile hotspot, then set the profile bind address to the laptop's hotspot-assigned IPv4 address or `0.0.0.0` and use the configured listener port on the POS.

Check Windows Firewall if the POS cannot connect. A hotspot may allow local client-to-client traffic, but some phones or carrier/device settings isolate clients. If the UAT endpoint is reachable only through an office VPN, verify that the VPN can connect over the mobile hotspot; disconnecting office LAN may remove the route to UAT. Internet is not required for laptop-to-POS local traffic, but is required for an internet-hosted UAT server.

Office VLAN routing, Wi-Fi client isolation, Windows Firewall and endpoint security may require IT approval. Do not bypass corporate controls.

## Multiple configurations

Profiles are stored locally in `data/profiles.json` beside the EXE (or in the project folder during Python development) and are not committed by default. Example profiles are in `config/profiles.example.json`. Each profile owns an upstream host/port, bind address/listen port, TCP/TLS label and independent fault settings. Import can merge with existing profiles or explicitly replace them.

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
