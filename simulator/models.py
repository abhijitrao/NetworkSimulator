"""Validated configuration models for independent proxy profiles."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import uuid


@dataclass
class FaultSettings:
    latency_ms: int = 0
    jitter_ms: int = 0
    bandwidth_bytes_per_second: int = 0
    pause_client_to_upstream: bool = False
    pause_upstream_to_client: bool = False

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "FaultSettings":
        value = value or {}
        return cls(
            latency_ms=int(value.get("latency_ms", 0)),
            jitter_ms=int(value.get("jitter_ms", 0)),
            bandwidth_bytes_per_second=int(value.get("bandwidth_bytes_per_second", 0)),
            pause_client_to_upstream=bool(value.get("pause_client_to_upstream", False)),
            pause_upstream_to_client=bool(value.get("pause_upstream_to_client", False)),
        )

    def validate(self) -> None:
        if self.latency_ms < 0 or self.jitter_ms < 0 or self.bandwidth_bytes_per_second < 0:
            raise ValueError("Fault values cannot be negative")


@dataclass
class ProxyProfile:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "New profile"
    upstream_host: str = "127.0.0.1"
    upstream_port: int = 9000
    bind_host: str = "0.0.0.0"
    listen_port: int = 8666
    transport_label: str = "tcp"
    enabled: bool = True
    connect_timeout_ms: int = 10000
    notes: str = ""
    fault_profile: FaultSettings = field(default_factory=FaultSettings)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ProxyProfile":
        profile = cls(
            id=str(value.get("id") or uuid.uuid4()),
            name=str(value.get("name", "New profile")).strip(),
            upstream_host=str(value.get("upstream_host", "127.0.0.1")).strip(),
            upstream_port=int(value.get("upstream_port", 9000)),
            bind_host=str(value.get("bind_host", "127.0.0.1")).strip(),
            listen_port=int(value.get("listen_port", 8666)),
            transport_label=str(value.get("transport_label", "tcp")).lower(),
            enabled=bool(value.get("enabled", True)),
            connect_timeout_ms=int(value.get("connect_timeout_ms", 10000)),
            notes=str(value.get("notes", "")),
            fault_profile=FaultSettings.from_dict(value.get("fault_profile")),
        )
        profile.validate()
        return profile

    def validate(self) -> None:
        if not self.id or not self.name or not self.upstream_host or not self.bind_host:
            raise ValueError("Profile id, name, upstream host and bind host are required")
        if not 1 <= self.upstream_port <= 65535 or not 1 <= self.listen_port <= 65535:
            raise ValueError("Ports must be between 1 and 65535")
        if self.transport_label not in {"tcp", "tls_passthrough"}:
            raise ValueError("transport_label must be 'tcp' or 'tls_passthrough'")
        if not 100 <= self.connect_timeout_ms <= 300000:
            raise ValueError("connect_timeout_ms must be between 100 and 300000")
        self.fault_profile.validate()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
