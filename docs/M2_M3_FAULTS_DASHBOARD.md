# M2 + M3 — Fault Injection and Dashboard

## Included

- Live per-profile latency and jitter (applied to each forwarded read chunk).
- Directional bandwidth throttling.
- Directional forwarding pause/resume. Pausing upstream-to-client forwarding simulates a server response stall while the POS read timeout can expire; it is not a TCP connect timeout.
- Best-effort active connection abort by closing both sockets. Exact RST semantics are OS-dependent and are not promised.
- HTML dashboard with profile create/edit/duplicate/delete, start/stop, start-all/stop-all, status polling, connection counters, fault controls, and JSON import/export.
- Management API bound to loopback only.

## Launch

1. Use an approved Python 3.10+ runtime.
2. Install Flask in the permitted user environment: `python -m pip install --user -r requirements.txt`.
3. Run `start.bat` or `python app.py`.
4. Open `http://127.0.0.1:5050`.
5. Add a profile. Use `127.0.0.1` bind for local testing; use the laptop LAN IPv4 or `0.0.0.0` only on a trusted and approved network to accept POS connections.
6. Start the profile and point the POS app to the laptop IP and listener port. For TLS, retain the original upstream hostname as the TLS peer identity in the POS client.

## Scenario semantics

- Latency/jitter are applied before forwarding each received stream chunk, separately in each direction. They are application-stream delays, not precise packet-level network emulation.
- Bandwidth is throttled by delaying each received chunk based on its byte count and configured bytes/second.
- Pause POS-to-server stops forwarding requests; pause server-to-POS stops forwarding responses. Both are reversible without restarting the listener.
- Abort closes current client and upstream sockets. Windows and POS TCP stacks may report different error codes depending on timing.
- No TCP payload is logged or persisted.

## Office network / permissions

The dashboard listens only on loopback. Proxy listeners need a reachable laptop interface. Different office LAN/Wi-Fi VLANs, client isolation, firewall rules, or endpoint controls may block POS-to-laptop connectivity. Do not bypass corporate policy; request an approved firewall/routing exception if needed. The app does not install services, drivers, certificates, or system-wide components.

## Current limitations

- User-space TCP relay does not simulate actual IP packet loss, SYN blackholes, Wi-Fi disassociation, or device-wide internet loss.
- TLS is opaque passthrough; certificate tests must be performed by the POS TLS client against a test server with the appropriate certificate configuration.
- Dashboard is local-only and intentionally has no remote administration/authentication surface.
