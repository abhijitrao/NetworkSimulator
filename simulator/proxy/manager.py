"""Lifecycle manager for multiple independent proxy profiles."""
from __future__ import annotations

import logging
import threading
from ..models import ProxyProfile
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
                if runtime.running and runtime.profile.bind_host == profile.bind_host and runtime.profile.listen_port == profile.listen_port:
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

    def status(self) -> list[dict]:
        with self._lock:
            return [{
                "profile_id": profile_id,
                "name": runtime.profile.name,
                "running": runtime.running,
                "active_connections": len(runtime.active_connections),
                "listen_host": runtime.profile.bind_host,
                "listen_port": runtime.profile.listen_port,
            } for profile_id, runtime in self._runtimes.items()]
