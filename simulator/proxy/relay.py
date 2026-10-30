"""Concurrent, byte-preserving TCP relay. TLS is forwarded as opaque bytes."""
from __future__ import annotations

import logging
import socket
import socketserver
import threading
from dataclasses import dataclass
from typing import Callable

from ..models import ProxyProfile

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
        self._connections: dict[str, ConnectionInfo] = {}
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
        server.runtime = self  # type: ignore[attr-defined]
        self._server = server
        self._stopping.clear()
        self._thread = threading.Thread(target=server.serve_forever, name=f"proxy-{self.profile.id}", daemon=True)
        self._thread.start()
        LOG.info("Proxy '%s' listening on %s:%s -> %s:%s", self.profile.name, self.profile.bind_host,
                 self.profile.listen_port, self.profile.upstream_host, self.profile.upstream_port)

    def stop(self) -> None:
        self._stopping.set()
        server, self._server = self._server, None
        if server:
            server.shutdown()
            server.server_close()
        with self._lock:
            active = list(self._connections.values())
        # Active sockets are closed by their handler threads when their peer closes.
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
        self._thread = None
        LOG.info("Proxy '%s' stopped", self.profile.name)

    def _notify(self) -> None:
        if self.on_connection_change:
            try:
                self.on_connection_change()
            except Exception:
                LOG.exception("Connection-change callback failed")

    def _handle_client(self, client: socket.socket, address: tuple) -> None:
        import time
        import uuid
        connection_id = uuid.uuid4().hex[:12]
        info = ConnectionInfo(connection_id, f"{address[0]}:{address[1]}", time.time())
        upstream: socket.socket | None = None
        try:
            client.settimeout(None)
            upstream = socket.create_connection(
                (self.profile.upstream_host, self.profile.upstream_port),
                timeout=self.profile.connect_timeout_ms / 1000.0,
            )
            upstream.settimeout(None)
            with self._lock:
                self._connections[connection_id] = info
            self._notify()
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
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    try:
                        sock.close()
                    except OSError:
                        pass
            with self._lock:
                self._connections.pop(connection_id, None)
            self._notify()

    @staticmethod
    def _pump(source: socket.socket, destination: socket.socket, info: ConnectionInfo, direction: str) -> None:
        counter = "bytes_from_client" if direction == "client" else "bytes_from_upstream"
        try:
            while True:
                chunk = source.recv(65536)
                if not chunk:
                    try:
                        destination.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                    return
                destination.sendall(chunk)
                setattr(info, counter, getattr(info, counter) + len(chunk))
        except (ConnectionResetError, BrokenPipeError, OSError) as exc:
            LOG.debug("[%s] %s relay ended: %s", info.connection_id, direction, exc)
            try:
                destination.shutdown(socket.SHUT_WR)
            except OSError:
                pass
