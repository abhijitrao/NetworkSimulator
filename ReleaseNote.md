# Network Simulator — Release Notes

This file tracks the user-facing changes included in each stable release.

## v1.6 — Stable Release

### Traffic Event Log
- Added smart auto-scroll to keep the latest traffic events visible by default.
- Auto-scroll pauses when the user scrolls up to inspect earlier events.
- Added a floating **↓ Latest** control to jump to the newest events and resume auto-scroll.
- New traffic events are appended incrementally, avoiding unnecessary re-rendering of existing rows.
- Added a subtle fade-in effect for newly received log rows.
- Preserved the existing event filter, raw request/response chunk association and 200-row display limit.

### Processing Code Rules and TCP response handling
- Fixed response forwarding when Processing Code Rules contain Block rules but an incoming response belongs to an unmatched Processing Code.
- Improved handling of fragmented/partial ISO8583 TCP response frames so chunks are not dropped while the proxy waits for the complete frame.
- Kept configured Alter Response processing active when a matching rule is present.

### Dashboard and profile workflow
- Preserved the dashboard scroll position when profile or feature edit dialogs close.
- After saving an existing profile, the dashboard asks whether to start that profile's proxy. Choosing **Yes** starts it; **No** leaves it stopped.
- New-profile creation retains its existing save-only behavior.

## v1.5 — Stable Release

### Alter Response bug fix
- Fixed the Alter Response feature so a configured custom response HEX payload can be used without applying ISO8583 frame-length or MTI validation.
- Continued validating that the input is non-empty, contains an even number of HEX characters, and contains only valid HEX characters.
- The configured replacement bytes are forwarded to the POS without rewriting the payload.

## v1.4 — Stable Release

### Per-Processing-Code TCP response rules
- Added profile-specific Processing Code (DE 3) rules for plain TCP connections.
- Added three actions for a matching Processing Code:
  - **No Action** — forward traffic normally.
  - **Block** — do not forward the matching request to the upstream host; the POS receives no response and can reach its timeout handling.
  - **Alter Response** — forward the request and replace the matching server response frame with the configured HEX response.
- Added per-code action editing in the Processing Code Rules dialog, including custom HEX response input.
- Preserved existing Processing Code configuration, request-sequence blocking and fault-injection settings.
- Processing Code response rules are not applied to TLS passthrough connections.

## v1.3 — Stable Release

### Request Sequence Blocking
- Added request-sequence blocking independently for each endpoint profile.
- Added profile-level enable/disable control, blocked request numbers, an independent counter and a reset action.
- Selected requests are forwarded to the upstream server, but their responses are suppressed so the POS can exercise its timeout handling.
- Persisted sequence-blocking settings with the endpoint profile.
- Updated dashboard terminology from **POS** to **App** where appropriate.

## v1.2 — Stable Release

### TLS Traffic Logging
- Added Traffic Event Log entries for TLS passthrough connection, request, response, disconnect and upstream connection-error events.
- Added TLS request/response byte counts and transport identification.
- Added optional raw encrypted TLS request/response HEX capture.
- Raw TLS capture remains opt-in and uses a bounded preview per chunk, with truncation indication.
- TLS traffic is logged as opaque forwarded TCP stream data; the simulator does not decrypt TLS or parse application-level ISO8583 messages.

### Traffic Log improvements
- Added a full-screen Traffic Event Log view with internal scrolling and Escape/exit support.
- Added **Export Logs (.txt)**, including retained event rows and optional raw HEX rows.
- Exported events are ordered chronologically (oldest first) and use fixed-width aligned columns.
- Removed Connection ID from the exported text log.
- Improved event lifecycle logging to avoid duplicate CONNECTED/DISCONNECTED events and duplicate connection-error entries.
- Improved traffic table labels, toolbar alignment and responsive layout.

## v1.1 — Stable Release

### ISO8583 Traffic Diagnostics
- Added ISO8583 request/response metadata to traffic events.
- Added inline raw HEX diagnostics associated with the relevant traffic events.
- Removed raw request/response HEX entries from the Traffic Log filter dropdown.
- Corrected regression coverage for normal response metadata parsing.

## v1.0 — Initial Stable Release

### Core TCP Proxy
- Added a concurrent, bidirectional, byte-preserving TCP relay.
- Added support for multiple independent endpoint profiles and listener ports.
- Added opaque TLS passthrough without TLS termination or certificate-validation bypass.
- Added atomic JSON profile persistence and profile collision validation.

### Network Fault Simulation
- Added per-profile direction selection: **Request** (POS → Server), **Response** (Server → POS), or **Both**. Request is the default.
- Added directional latency, jitter and bandwidth throttling.
- Added directional traffic pause/resume.
- Added Normal, Slow (30 seconds), Very Slow (55 seconds), Unstable and No Response presets.
- Added best-effort active connection abort.

### Local Dashboard
- Added a localhost-only Flask management API and browser dashboard.
- Added profile create, edit, duplicate, delete, start/stop and start-all/stop-all controls.
- Added live profile status, active connection details and byte counters.
- Added POS connection details with detected laptop IPv4 address, adapter selection, refresh and IP:port copy.
- Added JSON profile import/export with merge or replace options.

### Security and operating notes
- TLS is forwarded as opaque bytes. Certificate-chain validation, hostname verification, SNI and certificate pinning remain end-to-end between the POS and server.
- The simulator does not log payment/application payloads by default.
- The management API is restricted to localhost.
- True IP packet loss, SYN blackholes, Wi-Fi loss and device-wide internet outage require an approved network gateway or firewall; they cannot be fully simulated by the local TCP proxy alone.

---

## Notes
- Release notes describe the changes included in each stable version.
- TLS passthrough logging does not decrypt TLS traffic.
- Processing Code (DE 3) Block/Alter Response rules are for plain TCP; TLS remains opaque passthrough.
