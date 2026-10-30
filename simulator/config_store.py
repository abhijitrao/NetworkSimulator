"""Atomic JSON persistence for multiple proxy profiles."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import threading
from .models import ProxyProfile


class ProfileStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[ProxyProfile]:
        with self._lock:
            if not self.path.exists():
                return []
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raise ValueError("Configuration root must be a JSON array")
            profiles = [ProxyProfile.from_dict(item) for item in raw]
            self._validate_unique(profiles)
            return profiles

    def save(self, profiles: list[ProxyProfile]) -> None:
        with self._lock:
            self._validate_unique(profiles)
            payload = json.dumps([p.to_dict() for p in profiles], indent=2)
            fd, temp_name = tempfile.mkstemp(prefix=self.path.name, suffix=".tmp", dir=self.path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp_name, self.path)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)

    @staticmethod
    def _listeners_conflict(left: ProxyProfile, right: ProxyProfile) -> bool:
        if left.listen_port != right.listen_port:
            return False
        wildcards = {"0.0.0.0", "::", ""}
        return left.bind_host == right.bind_host or left.bind_host in wildcards or right.bind_host in wildcards

    @staticmethod
    def _validate_unique(profiles: list[ProxyProfile]) -> None:
        ids = [p.id for p in profiles]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate profile IDs are not allowed")
        for profile in profiles:
            profile.validate()
        for index, profile in enumerate(profiles):
            for other in profiles[index + 1:]:
                if ProfileStore._listeners_conflict(profile, other):
                    raise ValueError(
                        f"Listener port collision: {profile.name} and {other.name} "
                        f"both conflict on port {profile.listen_port}"
                    )

    @staticmethod
    def import_profiles(current: list[ProxyProfile], imported: list[ProxyProfile], replace: bool = False) -> list[ProxyProfile]:
        ProfileStore._validate_unique(imported)
        if replace:
            return list(imported)
        merged = {p.id: p for p in current}
        for profile in imported:
            if profile.id in merged:
                raise ValueError(f"Profile ID already exists: {profile.id}")
            merged[profile.id] = profile
        result = list(merged.values())
        ProfileStore._validate_unique(result)
        return result
