"""Validated configuration models for independent proxy profiles."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import uuid


@dataclass
class FaultSettings:
    apply_to: str = "request"
    latency_ms: int = 0
    jitter_ms: int = 0
    bandwidth_bytes_per_second: int = 0
    pause_client_to_upstream: bool = False
    pause_upstream_to_client: bool = False

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "FaultSettings":
        value = value or {}
        return cls(
            apply_to=str(value.get("apply_to", "request")),
            latency_ms=int(value.get("latency_ms", 0)),
            jitter_ms=int(value.get("jitter_ms", 0)),
            bandwidth_bytes_per_second=int(value.get("bandwidth_bytes_per_second", 0)),
            pause_client_to_upstream=bool(value.get("pause_client_to_upstream", False)),
            pause_upstream_to_client=bool(value.get("pause_upstream_to_client", False)),
        )

    def validate(self) -> None:
        if self.apply_to not in {"request", "response", "both"}:
            raise ValueError("apply_to must be request, response or both")
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
    processing_codes: list[str] = field(default_factory=list)
    processing_rules_enabled: bool = True
    processing_code_rules: dict[str, dict[str, str]] = field(default_factory=dict)
    raw_hex_logging: bool = False
    request_sequence_enabled: bool = False
    request_sequence_orders: list[int] = field(default_factory=list)
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
            processing_codes=[str(code).strip() for code in value.get("processing_codes", []) if str(code).strip()],
            processing_rules_enabled=bool(value.get("processing_rules_enabled", True)),
            processing_code_rules={str(code).strip(): {str(k): str(v) for k, v in rule.items()} for code, rule in (value.get("processing_code_rules") or {}).items() if isinstance(rule, dict)},
            raw_hex_logging=bool(value.get("raw_hex_logging", False)),
            request_sequence_enabled=bool(value.get("request_sequence_enabled", False)),
            request_sequence_orders=sorted(set(int(order) for order in value.get("request_sequence_orders", []))),
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
        if self.transport_label == "tls_passthrough" and (self.processing_codes or self.processing_code_rules):
            raise ValueError("Processing Code rules are supported only for Plain TCP profiles")
        if any(order < 1 for order in self.request_sequence_orders):
            raise ValueError("Request sequence numbers must be greater than zero")
        self.request_sequence_orders = sorted(set(self.request_sequence_orders))
        if any(len(code) != 6 or not code.isdigit() for code in self.processing_codes):
            raise ValueError("Processing Codes must contain exactly 6 digits")
        self.processing_codes = list(dict.fromkeys(self.processing_codes))
        normalized_rules = {}
        for code, rule in self.processing_code_rules.items():
            action = rule.get("action", "block")
            response_hex = "".join(rule.get("response_hex", "").split()).upper()
            if len(code) != 6 or not code.isdigit():
                raise ValueError("Each Processing Code rule must contain exactly 6 digits")
            if action not in {"none", "block", "alter_response"}:
                raise ValueError("Processing Code action must be none, block or alter_response")
            if action == "alter_response":
                if not response_hex or len(response_hex) % 2 or any(ch not in "0123456789ABCDEF" for ch in response_hex):
                    raise ValueError(f"Processing Code {code}: response must be valid, even-length HEX")
                response = bytes.fromhex(response_hex)
                if len(response) < 17:
                    raise ValueError(f"Processing Code {code}: response must be a complete ISO8583 frame")
                from .proxy.iso8583 import decode_bcd_length, extract_mti
                if decode_bcd_length(response[:2]) != len(response) - 2:
                    raise ValueError(f"Processing Code {code}: response frame length does not match HEX payload")
                extract_mti(response)
            normalized_rules[code] = {"action": action, "response_hex": response_hex if action == "alter_response" else ""}
        self.processing_code_rules = normalized_rules
        if normalized_rules:
            self.processing_codes = list(normalized_rules)
        self.fault_profile.validate()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
