"""Lifecycle manager for multiple independent proxy profiles."""
from __future__ import annotations

import logging
import threading
from ..models import FaultSettings, ProxyProfile
from .relay import ProxyRuntime

LOG = logging.getLogger("posnet.manager")


class ProxyManager:
    def __init__(self, on_event=None):
        self._lock = threading.RLock()
        self._runtimes: dict[str, ProxyRuntime] = {}
        self.on_event = on_event
        self.raw_hex_logging = False
        self._sequence_lock = threading.RLock()
        self._sequence_settings: dict[str, dict] = {}

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
            self._sequence_settings.setdefault(profile.id, {
                "enabled": profile.request_sequence_enabled,
                "orders": set(profile.request_sequence_orders),
                "reset_on_end": profile.request_sequence_reset_on_end,
                "counter": 0,
            })
            runtime = ProxyRuntime(profile, on_event=self.on_event,
                                   on_request_accepted=lambda profile_id=profile.id: self._on_request_accepted(profile_id))
            runtime.set_raw_hex_logging(profile.raw_hex_logging or self.raw_hex_logging)
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

    def configure_request_sequence_fault(self, profile_id: str, enabled: bool, orders: list[int], reset_on_end: bool = False) -> dict:
        normalized = sorted(set(int(value) for value in orders))
        if any(value < 1 for value in normalized):
            raise ValueError("Request order numbers must be greater than zero")
        with self._sequence_lock:
            current = self._sequence_settings.setdefault(profile_id, {"enabled": False, "orders": set(), "reset_on_end": False, "counter": 0})
            changed = bool(enabled) != current["enabled"] or set(normalized) != current["orders"] or bool(reset_on_end) != current.get("reset_on_end", False)
            current["enabled"] = bool(enabled)
            current["orders"] = set(normalized)
            current["reset_on_end"] = bool(reset_on_end)
            if changed:
                current["counter"] = 0
            return self.request_sequence_status(profile_id)

    def reset_request_sequence_fault(self, profile_id: str) -> dict:
        with self._sequence_lock:
            current = self._sequence_settings.setdefault(profile_id, {"enabled": False, "orders": set(), "reset_on_end": False, "counter": 0})
            current["counter"] = 0
            return self.request_sequence_status(profile_id)

    def request_sequence_status(self, profile_id: str) -> dict:
        with self._sequence_lock:
            current = self._sequence_settings.setdefault(profile_id, {"enabled": False, "orders": set(), "reset_on_end": False, "counter": 0})
            return {
                "enabled": current["enabled"],
                "reset_on_end": current.get("reset_on_end", False),
                "orders": sorted(current["orders"]),
                "counter": current["counter"],
                "next_request": current["counter"] + 1,
            }

    def _on_request_accepted(self, profile_id: str) -> tuple[int, bool] | None:
        with self._sequence_lock:
            current = self._sequence_settings.setdefault(profile_id, {"enabled": False, "orders": set(), "reset_on_end": False, "counter": 0})
            if not current["enabled"]:
                return None
            current["counter"] += 1
            number = current["counter"]
            should_block = number in current["orders"]
            if current.get("reset_on_end", False) and should_block and number == max(current["orders"], default=0):
                current["counter"] = 0
            return number, should_block

    def set_raw_hex_logging(self, enabled: bool) -> None:
        with self._lock:
            self.raw_hex_logging = bool(enabled)
            runtimes = list(self._runtimes.values())
        for runtime in runtimes:
            runtime.set_raw_hex_logging(self.raw_hex_logging)

    def set_fault(self, profile_id: str, settings: FaultSettings) -> None:
        with self._lock:
            runtime = self._runtimes.get(profile_id)
        if not runtime or not runtime.running:
            raise ValueError("Proxy profile is not running")
        runtime.set_fault_settings(settings)

    def set_processing_codes(self, profile_id: str, codes: list[str], enabled: bool = True) -> None:
        with self._lock:
            runtime = self._runtimes.get(profile_id)
        if not runtime or not runtime.running:
            raise ValueError('Proxy profile is not running')
        if runtime.profile.transport_label != 'tcp':
            raise ValueError('Processing Code rules are supported only for Plain TCP profiles')
        runtime.profile.processing_codes = list(codes)
        runtime.profile.processing_rules_enabled = bool(enabled)

    def set_processing_code_rules(self, profile_id: str, rules: dict, enabled: bool = True) -> None:
        with self._lock:
            runtime = self._runtimes.get(profile_id)
        if not runtime or not runtime.running:
            raise ValueError("Proxy profile is not running")
        if runtime.profile.transport_label != "tcp":
            raise ValueError("Processing Code response rules are supported only for Plain TCP profiles")
        runtime.profile.processing_code_rules = {
            str(code): dict(rule) for code, rule in rules.items()
        }
        runtime.profile.processing_codes = list(runtime.profile.processing_code_rules)
        runtime.profile.processing_rules_enabled = bool(enabled)

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
