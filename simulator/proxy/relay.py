"""Concurrent byte-preserving TCP relay with live directional fault injection.

TLS is forwarded as opaque bytes. The proxy never terminates TLS or sees plaintext.
"""
from __future__ import annotations

import logging
from collections import deque
import random
import socket
import socketserver
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from ..models import FaultSettings, ProxyProfile
from .iso8583 import Iso8583FrameError, Iso8583StreamFramer, extract_mti, extract_processing_code

LOG = logging.getLogger("posnet.proxy")


@dataclass
class ConnectionInfo:
    connection_id: str
    client_address: str
    opened_at: float
    bytes_from_client: int = 0
    bytes_from_upstream: int = 0


class ProxyRuntime:
    def __init__(self, profile: ProxyProfile, on_connection_change: Callable[[], None] | None = None, on_event: Callable[[dict], None] | None = None, on_request_accepted: Callable[[], tuple[int, bool] | None] | None = None):
        self.profile = profile
        self.on_connection_change = on_connection_change
        self.on_event = on_event
        self.on_request_accepted = on_request_accepted
        self.raw_hex_logging = False
        self._lock = threading.RLock()
        self._fault_condition = threading.Condition(self._lock)
        self._fault = profile.fault_profile
        self._connections: dict[str, ConnectionInfo] = {}
        self._sockets: dict[str, set[socket.socket]] = {}
        self._server: socketserver.ThreadingTCPServer | None = None
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()

    @property
    def running(self) -> bool:
        return self._server is not None and self._thread is not None and self._thread.is_alive()

    @property
    def active_connections(self) -> list[ConnectionInfo]:
        with self._lock:
            return list(self._connections.values())

    def set_raw_hex_logging(self, enabled: bool) -> None:
        with self._lock:
            self.raw_hex_logging = bool(enabled)

    def set_fault_settings(self, settings: FaultSettings) -> None:
        settings.validate()
        with self._fault_condition:
            self._fault = settings
            self._fault_condition.notify_all()
        LOG.info("Fault settings updated for profile '%s'", self.profile.name)

    def get_fault_settings(self) -> FaultSettings:
        with self._lock:
            return FaultSettings.from_dict(vars(self._fault))

    def abort_connections(self) -> int:
        """Close all current client/upstream sockets (best-effort connection abort)."""
        with self._lock:
            sockets = [sock for group in self._sockets.values() for sock in group]
        for sock in sockets:
            self._close_socket(sock)
        return len(sockets)

    def start(self) -> None:
        if self.running:
            return
        runtime = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                runtime._handle_client(self.request, self.client_address)

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True
            block_on_close = False

        server = Server((self.profile.bind_host, self.profile.listen_port), Handler)
        self._server = server
        self._stopping.clear()
        self._thread = threading.Thread(target=server.serve_forever, name=f"proxy-{self.profile.id}", daemon=True)
        self._thread.start()
        LOG.info("Proxy '%s' listening on %s:%s -> %s:%s", self.profile.name, self.profile.bind_host,
                 self.profile.listen_port, self.profile.upstream_host, self.profile.upstream_port)

    def stop(self) -> None:
        self._stopping.set()
        with self._fault_condition:
            self._fault_condition.notify_all()
        server, self._server = self._server, None
        if server:
            server.shutdown()
            server.server_close()
        self.abort_connections()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
        self._thread = None
        LOG.info("Proxy '%s' stopped", self.profile.name)

    @staticmethod
    def _close_socket(sock: socket.socket) -> None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass

    def _notify(self) -> None:
        if self.on_connection_change:
            try:
                self.on_connection_change()
            except Exception:
                LOG.exception("Connection-change callback failed")

    def _handle_client(self, client: socket.socket, address: tuple) -> None:
        connection_id = uuid.uuid4().hex[:12]
        info = ConnectionInfo(connection_id, f"{address[0]}:{address[1]}", time.time())
        upstream: socket.socket | None = None
        connected = False
        is_tls = self.profile.transport_label == 'tls_passthrough'
        with self._lock:
            self._connections[connection_id] = info
            self._sockets[connection_id] = {client}
        self._notify()
        suppress_responses = threading.Event()
        suppressed_code = {'value': '', 'reason': 'Processing Code rule'}
        response_rule_queue = deque()
        response_rule_lock = threading.Lock()
        sequence_number = None
        try:
            sequence = self.on_request_accepted() if self.on_request_accepted else None
            if sequence is not None:
                sequence_number, block_response = sequence
                if block_response:
                    suppress_responses.set()
                    suppressed_code['reason'] = 'Request Sequence No Response fault'
                    self._emit_event('SEQUENCE_BLOCKED', info, detail=f'Request #{sequence_number} selected for No Response; request will be forwarded and host response suppressed', mti='TLS' if is_tls else '')
                else:
                    self._emit_event('SEQUENCE_REQUEST', info, detail=f'Request #{sequence_number} allowed', mti='TLS' if is_tls else '')
            if self._stopping.is_set():
                return
            client.settimeout(None)
            upstream = socket.create_connection(
                (self.profile.upstream_host, self.profile.upstream_port),
                timeout=self.profile.connect_timeout_ms / 1000.0,
            )
            upstream.settimeout(None)
            with self._lock:
                self._sockets[connection_id].add(upstream)
            if self._stopping.is_set():
                return
            connected = True
            LOG.info("[%s] Connected client %s", connection_id, info.client_address)
            self._emit_event('CONNECTED', info, detail='TLS passthrough tunnel connected' if is_tls else 'TCP connection established', mti='TLS' if is_tls else '')
            workers = [
                threading.Thread(target=self._pump, args=(client, upstream, info, "client", suppress_responses, suppressed_code), daemon=True),
                threading.Thread(target=self._pump, args=(upstream, client, info, "upstream", suppress_responses, suppressed_code), daemon=True),
            ]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()
            LOG.info("[%s] Closed; client->upstream=%d bytes, upstream->client=%d bytes",
                     connection_id, info.bytes_from_client, info.bytes_from_upstream)
        except (OSError, TimeoutError) as exc:
            LOG.warning("[%s] Connection failed: %s", connection_id, exc)
            self._emit_event('CONNECTION_ERROR', info, detail=f'Upstream connection failed: {exc}', mti='TLS' if is_tls else '')
        finally:
            for sock in (client, upstream):
                if sock:
                    self._close_socket(sock)
            if connected:
                self._emit_event(
                    'DISCONNECTED', info,
                    detail=f'Connection closed; POS → Server {info.bytes_from_client} B, Server → POS {info.bytes_from_upstream} B',
                    mti='TLS' if is_tls else '',
                )
            with self._lock:
                self._connections.pop(connection_id, None)
                self._sockets.pop(connection_id, None)
            self._notify()

    def _fault_snapshot(self) -> FaultSettings:
        with self._lock:
            return FaultSettings.from_dict(vars(self._fault))

    def _wait_for_forwarding(self, direction: str) -> bool:
        pause_key = "pause_client_to_upstream" if direction == "client" else "pause_upstream_to_client"
        with self._fault_condition:
            while getattr(self._fault, pause_key) and not self._stopping.is_set():
                self._fault_condition.wait(timeout=0.2)
            return not self._stopping.is_set()

    def _emit_event(self, event_type: str, info: ConnectionInfo, processing_code: str = '', detail: str = '', mti: str = '') -> None:
        if self.on_event:
            try:
                self.on_event({'timestamp': time.time(), 'profile_id': self.profile.id, 'profile': self.profile.name, 'connection_id': info.connection_id, 'type': event_type, 'processing_code': processing_code, 'mti': mti, 'detail': detail})
            except Exception:
                LOG.exception('Event callback failed')

    @staticmethod
    def _raw_hex_detail(chunk: bytes) -> str:
        preview = chunk[:4096].hex().upper()
        suffix = f'... [truncated; {len(chunk)} bytes total]' if len(chunk) > 4096 else ''
        return f'HEX chunk ({len(chunk)} bytes): {preview}{suffix}'

    def _pump(self, source: socket.socket, destination: socket.socket, info: ConnectionInfo, direction: str, suppress_responses: threading.Event, suppressed_code: dict) -> None:
        counter = "bytes_from_client" if direction == "client" else "bytes_from_upstream"
        framer = Iso8583StreamFramer() if self.profile.transport_label == 'tcp' else None
        is_tls = self.profile.transport_label == 'tls_passthrough'
        try:
            while not self._stopping.is_set():
                if not self._wait_for_forwarding(direction):
                    return
                chunk = source.recv(65536)
                if not chunk:
                    # If responses are intentionally suppressed, keep the POS-side
                    # socket open so its own read timeout fires instead of EOF.
                    if not (direction == 'upstream' and suppress_responses.is_set()):
                        try:
                            destination.shutdown(socket.SHUT_WR)
                        except OSError:
                            pass
                    return
                # Re-check after recv: a live pause may have been enabled while recv was blocked.
                if not self._wait_for_forwarding(direction):
                    return

                if direction == 'upstream':
                    if self.raw_hex_logging and not is_tls:
                        self._emit_event('RAW_RESPONSE', info, suppressed_code['value'], self._raw_hex_detail(chunk))
                    if suppress_responses.is_set():
                        self._emit_event('RESPONSE', info, suppressed_code['value'], 'Server response received')
                        self._emit_event('DROPPED', info, suppressed_code['value'], f'Server response suppressed by {suppressed_code["reason"]}')
                        continue

                if direction == 'client' and self.raw_hex_logging and not is_tls:
                    # Plain TCP diagnostics are captured before ISO8583 filtering, as before.
                    self._emit_event('RAW_REQUEST', info, detail=self._raw_hex_detail(chunk))

                outgoing_chunks = [chunk]
                if framer is not None:
                    try:
                        frames = framer.feed(chunk)
                    except Iso8583FrameError as exc:
                        self._emit_event('PARSE_ERROR', info, detail=str(exc))
                        outgoing_chunks = [framer.take_pending()]
                        framer = None  # Fail open and preserve buffered plus current bytes.
                        if direction == 'upstream':
                            self._emit_event('RESPONSE', info, suppressed_code['value'], 'Server response received')
                    else:
                        if direction == 'upstream':
                            # Keep response frames aligned with requests on this TCP stream.
                            # This App opens one transaction connection per request.
                            for frame in frames:
                                try:
                                    code = extract_processing_code(frame) or ''
                                    mti = extract_mti(frame)
                                except Iso8583FrameError as exc:
                                    self._emit_event('PARSE_ERROR', info, detail=str(exc))
                                    code, mti = '', ''
                                self._emit_event('RESPONSE', info, code, 'Server response received', mti)
                            if self.profile.processing_rules_enabled and self.profile.processing_code_rules:
                                outgoing_chunks = []
                                for frame in frames:
                                    with response_rule_lock:
                                        action_rule = response_rule_queue.popleft() if response_rule_queue else None
                                    if action_rule and action_rule['action'] == 'alter_response':
                                        replacement = bytes.fromhex(action_rule['response_hex'])
                                        outgoing_chunks.append(replacement)
                                        self._emit_event('RESPONSE_REPLACED', info, action_rule['code'],
                                                         f'Original server response replaced with configured HEX ({len(replacement)} bytes)', mti)
                                    else:
                                        outgoing_chunks.append(frame)
                        # With no suppression rules, inspect complete request frames
                        # for metadata but forward every original TCP chunk immediately.
                        elif not self.profile.processing_rules_enabled or not self.profile.processing_codes or not self.profile.processing_code_rules:
                            outgoing_chunks = [chunk]
                            for frame in frames:
                                try:
                                    code = extract_processing_code(frame)
                                    mti = extract_mti(frame)
                                except Iso8583FrameError as exc:
                                    self._emit_event('PARSE_ERROR', info, detail=str(exc))
                                    continue
                                self._emit_event('REQUEST', info, code or '', 'ISO8583 request', mti)
                        else:
                            outgoing_chunks = []
                            for frame in frames:
                                try:
                                    code = extract_processing_code(frame)
                                except Iso8583FrameError as exc:
                                    self._emit_event('PARSE_ERROR', info, detail=str(exc))
                                    outgoing_chunks.append(frame)
                                    with response_rule_lock:
                                        response_rule_queue.append(None)
                                    continue
                                self._emit_event('REQUEST', info, code or '', 'ISO8583 request', extract_mti(frame))
                                rule = self.profile.processing_code_rules.get(code or '') if self.profile.processing_rules_enabled else None
                                if rule:
                                    action = rule.get('action', 'block')
                                    with response_rule_lock:
                                        response_rule_queue.append({"action": action, "response_hex": rule.get("response_hex", ""), "code": code})
                                    suppressed_code['value'] = code
                                    if action == 'block':
                                        suppress_responses.set()
                                        suppressed_code['reason'] = 'Processing Code Block rule'
                                        self._emit_event('MATCHED', info, code, 'Request forwarded; server response will be blocked')
                                    elif action == 'alter_response':
                                        self._emit_event('MATCHED', info, code, 'Request forwarded; server response will be replaced')
                                    else:
                                        self._emit_event('MATCHED', info, code, 'No Action; request and server response will be forwarded')
                                else:
                                    with response_rule_lock:
                                        response_rule_queue.append(None)
                                outgoing_chunks.append(frame)
                        # Partial frames remain buffered until the next TCP chunk.

                if not outgoing_chunks:
                    continue

                settings = self._fault_snapshot()
                applies = settings.apply_to == "both" or (settings.apply_to == "request" and direction == "client") or (settings.apply_to == "response" and direction == "upstream")
                delay_ms = settings.latency_ms if applies else 0
                if applies and settings.jitter_ms:
                    delay_ms += random.uniform(-settings.jitter_ms, settings.jitter_ms)
                if delay_ms > 0 and self._stopping.wait(delay_ms / 1000.0):
                    return

                rate = settings.bandwidth_bytes_per_second if applies else 0
                if rate > 0 and self._stopping.wait(len(chunk) / rate):
                    return

                forwarded_bytes = 0
                for outgoing in outgoing_chunks:
                    destination.sendall(outgoing)
                    forwarded_bytes += len(outgoing)
                    setattr(info, counter, getattr(info, counter) + len(outgoing))

                if is_tls:
                    # A TLS TCP chunk is opaque encrypted data, not an ISO8583 frame.
                    # Emit transfer metadata only after sendall succeeds, so logs reflect
                    # bytes actually forwarded through the tunnel.
                    if self.raw_hex_logging:
                        raw_type = 'RAW_REQUEST' if direction == 'client' else 'RAW_RESPONSE'
                        self._emit_event(raw_type, info, detail='Encrypted TLS ' + self._raw_hex_detail(chunk))
                    event_type = 'REQUEST' if direction == 'client' else 'RESPONSE'
                    flow = 'POS → Server' if direction == 'client' else 'Server → POS'
                    self._emit_event(
                        event_type, info,
                        detail=f'Encrypted TLS data forwarded {flow} ({forwarded_bytes} bytes)',
                        mti='TLS',
                    )
        except (ConnectionResetError, BrokenPipeError, OSError) as exc:
            LOG.debug("[%s] %s relay ended: %s", info.connection_id, direction, exc)
            try:
                destination.shutdown(socket.SHUT_WR)
            except OSError:
                pass
