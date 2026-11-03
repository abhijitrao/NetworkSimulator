# Configuration Schema

The simulator supports multiple independent endpoint profiles. A profile maps one local TCP listener to one upstream TCP endpoint.

## Profile fields

- `id`: immutable UUID.
- `name`: user-facing profile name.
- `upstream_host`: hostname or IP of the actual test server.
- `upstream_port`: upstream TCP port.
- `bind_host`: local interface address; default should be an explicit user choice, not an unrestricted wildcard.
- `listen_port`: unique local port.
- `transport_label`: `tcp` or `tls_passthrough`; both use opaque TCP byte forwarding.
- `enabled`: whether the profile is eligible to start.
- `fault_profile`: default fault parameters.
- `connect_timeout_ms`: upstream connection timeout.
- `notes`: optional non-sensitive description.

## Operations

- Create, update, duplicate, delete.
- Start/stop one proxy.
- Start/stop all valid enabled profiles.
- Import/export profile collections as JSON.
- Validate required fields, port ranges, host values, and listener collisions before start.
- Keep profile IDs stable across edits and imports; report duplicate IDs rather than silently replacing.
- Persist updates atomically and preserve existing profiles when an import is merged.
- Provide an explicit replace-import mode with a confirmation step in the UI.

## Processing Code Rules (Plain TCP only)

- `processing_code_rules` is a profile-scoped object keyed by the exact six-digit DE 3 value.
- Each rule has `action`: `none`, `block`, or `alter_response`.
- `none` forwards the original request and response.
- `block` does not forward the matching request to the upstream host. The POS receives no response and can reach its configured read timeout.
- `alter_response` forwards the request, then replaces the corresponding complete server response frame with `response_hex`.
- `response_hex` must be an even-length HEX string containing a complete two-byte-length-prefixed ISO8583 frame. The declared frame length and MTI are validated before saving.
- Rules are persisted independently per profile. They are unavailable for TLS passthrough because TLS payloads remain encrypted and opaque.

## Fault settings

Faults are scoped to a profile and independently applied to POS-to-upstream and upstream-to-POS directions:
- latency_ms
- jitter_ms
- bandwidth_bytes_per_second
- forwarding_paused

Connection abort and upstream connect failure are connection-level actions. Do not drop bytes from a TCP stream and call it packet loss.

## Security and data

- Bind management APIs to loopback only.
- Bind proxy listeners only to an explicitly selected interface.
- Do not log application payloads or payment data.
- TLS remains end-to-end. Do not install a root CA, terminate TLS, weaken certificate verification, or collect decrypted data.

## Profile-specific request sequence fault

- Each endpoint profile has independent request sequence settings: `request_sequence_enabled` and `request_sequence_orders`.
- One newly accepted POS TCP connection counts as one request for that profile; this relies on the POS opening a new connection for each request.
- Configure comma-separated positive request numbers, for example `2, 3, 5`.
- Selected requests are forwarded to the upstream host, while upstream response bytes are suppressed so the POS receives no response and can reach its own timeout handling.
- Each profile has its own counter. Resetting or changing that profile's enabled state / configured order list restarts only that profile's counter at request 1.
- Settings are persisted with the endpoint profile. Runtime counters start at zero when the simulator process starts.
