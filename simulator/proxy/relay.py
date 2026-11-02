"""Concurrent byte-preserving TCP relay with live directional fault injection.

TLS is forwarded as opaque bytes. The proxy never terminates TLS or sees plaintext.
"""
from __future__ import annotations

import logging
import random
import socket
import socketserver
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from ..models import FaultSettings, ProxyProfile
from .iso8583 import Iso8583FrameError, Iso8583StreamFramer, extract_processing_code

LOG = logging.getLogger("posnet.proxy")


@dataclass
class ConnectionInfo:
    connection_id: str
    client_address: str
    opened_at: float
    bytes_from_client: int = 0
    bytes_from_upstream: int = 0


class ProxyRuntime:
    def __init__(self, profile: ProxyProfile, on_connection_change: Callable[[], None] | None = None, on_event: Callable[[dict], None] | None = None):
        self.profile = profile
        self.on_connection_change = on_connection_change
        self.on_event = on_event
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
        with self._lock:
            self._connections[connection_id] = info
            self._sockets[connection_id] = {client}
        self._notify()
        suppress_responses = threading.Event()
        suppressed_code = {'value': ''}
        try:
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
            LOG.info("[%s] Connected client %s", connection_id, info.client_address)
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
        finally:
            for sock in (client, upstream):
                if sock:
                    self._close_socket(sock)
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

    def _emit_event(self, event_type: str, info: ConnectionInfo, processing_code: str = '', detail: str = '') -> None:
        if self.on_event:
            try:
                self.on_event({'timestamp': time.time(), 'profile_id': self.profile.id, 'profile': self.profile.name, 'connection_id': info.connection_id, 'type': event_type, 'processing_code': processing_code, 'detail': detail})
            except Exception:
                LOG.exception('Event callback failed')

    def _pump(self, source: socket.socket, destination: socket.socket, info: ConnectionInfo, direction: str, suppress_responses: threading.Event, suppressed_code: dict) -> None:
        counter = "bytes_from_client" if direction == "client" else "bytes_from_upstream"
        framer = Iso8583StreamFramer() if direction == 'client' and self.profile.transport_label == 'tcp' and self.profile.processing_codes else None
        request_started = False
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
                    self._emit_event('RESPONSE', info, suppressed_code['value'], 'Server response received')
                    if suppress_responses.is_set():
                        self._emit_event('DROPPED', info, suppressed_code['value'], 'Server response suppressed by Processing Code rule')
                        continue

                if direction == 'client' and self.raw_hex_logging:
                    # Diagnostic only: keep capture in memory and bound each event.
                    preview = chunk[:4096].hex().upper()
                    suffix = f'... [truncated; {len(chunk)} bytes total]' if len(chunk) > 4096 else ''
                    self._emit_event('RAW_REQUEST', info, detail=f'HEX chunk ({len(chunk)} bytes): {preview}{suffix}')

                if direction == 'client' and not request_started:
                    # Log the POS-side request as soon as bytes arrive, even if the
                    # configured ISO8583 framing cannot decode this stream.
                    self._emit_event('REQUEST_RECEIVED', info, detail='POS request data received')
                    request_started = True

                outgoing_chunks = [chunk]
                if framer is not None:
                    try:
                        frames = framer.feed(chunk)
                    except Iso8583FrameError as exc:
                        self._emit_event('PARSE_ERROR', info, detail=str(exc))
                        outgoing_chunks = [framer.take_pending()]
                        framer = None  # Fail open and preserve buffered plus current bytes.
                    else:
                        outgoing_chunks = []
                        for frame in frames:
                            try:
                                code = extract_processing_code(frame)
                            except Iso8583FrameError as exc:
                                self._emit_event('PARSE_ERROR', info, detail=str(exc))
                                outgoing_chunks.append(frame)
                                continue
                            self._emit_event('REQUEST', info, code or '', 'ISO8583 request')
                            if code and code in self.profile.processing_codes:
                                rule_direction = self._fault_snapshot().apply_to
                                if rule_direction in {'response', 'both'}:
                                    suppress_responses.set()
                                    suppressed_code['value'] = code
                                if rule_direction in {'request', 'both'}:
                                    self._emit_event('DROPPED', info, code, 'Request suppressed by Processing Code rule')
                                    continue
                                self._emit_event('MATCHED', info, code, 'Request forwarded; server response suppression armed')
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

                for outgoing in outgoing_chunks:
                    destination.sendall(outgoing)
                    setattr(info, counter, getattr(info, counter) + len(outgoing))
        except (ConnectionResetError, BrokenPipeError, OSError) as exc:
            LOG.debug("[%s] %s relay ended: %s", info.connection_id, direction, exc)
            try:
                destination.shutdown(socket.SHUT_WR)
            except OSError:
                pass
