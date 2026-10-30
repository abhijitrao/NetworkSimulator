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
