"""Lifecycle manager for multiple independent proxy profiles."""
from __future__ import annotations

import logging
import threading
from ..models import FaultSettings, ProxyProfile
from .relay import ProxyRuntime

LOG = logging.getLogger("posnet.manager")


class ProxyManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._runtimes: dict[str, ProxyRuntime] = {}

    def start(self, profile: ProxyProfile) -> None:
        profile.validate()
        with self._lock:
            if profile.id in self._runtimes and self._runtimes[profile.id].running:
                return
            for profile_id, runtime in self._runtimes.items():
                if runtime.running and runtime.profile.listen_port == profile.listen_port and (
                    runtime.profile.bind_host == profile.bind_host or
                    runtime.profile.bind_host in {"0.0.0.0", "::"} or profile.bind_host in {"0.0.0.0", "::"}
                ):
                    raise ValueError(f"Listener port {profile.listen_port} is already used by profile {profile_id}")
            runtime = ProxyRuntime(profile)
            runtime.start()
            self._runtimes[profile.id] = runtime

    def stop(self, profile_id: str) -> None:
        with self._lock:
            runtime = self._runtimes.pop(profile_id, None)
        if runtime:
            runtime.stop()

    def stop_all(self) -> None:
        with self._lock:
            runtimes = list(self._runtimes.values())
            self._runtimes.clear()
        for runtime in runtimes:
            runtime.stop()

    def set_fault(self, profile_id: str, settings: FaultSettings) -> None:
        with self._lock:
            runtime = self._runtimes.get(profile_id)
        if not runtime or not runtime.running:
            raise ValueError("Proxy profile is not running")
        runtime.set_fault_settings(settings)

    def abort_connections(self, profile_id: str) -> int:
        with self._lock:
            runtime = self._runtimes.get(profile_id)
        if not runtime or not runtime.running:
            raise ValueError("Proxy profile is not running")
        return runtime.abort_connections()

    def status(self) -> list[dict]:
        with self._lock:
            runtimes = list(self._runtimes.items())
        result = []
        for profile_id, runtime in runtimes:
            connections = runtime.active_connections
            result.append({
                "profile_id": profile_id,
                "name": runtime.profile.name,
                "running": runtime.running,
                "active_connections": len(connections),
                "connections": [{
                    "id": item.connection_id,
                    "client": item.client_address,
                    "opened_at": item.opened_at,
                    "bytes_from_client": item.bytes_from_client,
                    "bytes_from_upstream": item.bytes_from_upstream,
                } for item in connections],
                "listen_host": runtime.profile.bind_host,
                "listen_port": runtime.profile.listen_port,
                "upstream_host": runtime.profile.upstream_host,
                "upstream_port": runtime.profile.upstream_port,
                "fault_profile": vars(runtime.get_fault_settings()),
            })
        return result
