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

LOG = logging.getLogger("posnet.proxy")


@dataclass
class ConnectionInfo:
    connection_id: str
    client_address: str
    opened_at: float
    bytes_from_client: int = 0
    bytes_from_upstream: int = 0


class ProxyRuntime:
    def __init__(self, profile: ProxyProfile, on_connection_change: Callable[[], None] | None = None):
        self.profile = profile
        self.on_connection_change = on_connection_change
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
                threading.Thread(target=self._pump, args=(client, upstream, info, "client"), daemon=True),
                threading.Thread(target=self._pump, args=(upstream, client, info, "upstream"), daemon=True),
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

    def _pump(self, source: socket.socket, destination: socket.socket, info: ConnectionInfo, direction: str) -> None:
        counter = "bytes_from_client" if direction == "client" else "bytes_from_upstream"
        try:
            while not self._stopping.is_set():
                if not self._wait_for_forwarding(direction):
                    return
                chunk = source.recv(65536)
                if not chunk:
                    try:
                        destination.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                    return
                # Re-check after recv: a live pause may have been enabled while recv was blocked.
                if not self._wait_for_forwarding(direction):
                    return

                settings = self._fault_snapshot()
                delay_ms = settings.latency_ms
                if settings.jitter_ms:
                    delay_ms += random.uniform(-settings.jitter_ms, settings.jitter_ms)
                if delay_ms > 0 and self._stopping.wait(delay_ms / 1000.0):
                    return

                rate = settings.bandwidth_bytes_per_second
                if rate > 0 and self._stopping.wait(len(chunk) / rate):
                    return

                destination.sendall(chunk)
                setattr(info, counter, getattr(info, counter) + len(chunk))
        except (ConnectionResetError, BrokenPipeError, OSError) as exc:
            LOG.debug("[%s] %s relay ended: %s", info.connection_id, direction, exc)
            try:
                destination.shutdown(socket.SHUT_WR)
            except OSError:
                pass
