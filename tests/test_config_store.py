"""Tests for profile persistence, import merging and listener collision checks."""
import tempfile
import unittest
from pathlib import Path

from simulator.config_store import ProfileStore
from simulator.models import ProxyProfile


class ProfileStoreTests(unittest.TestCase):
    def test_round_trip_multiple_profiles(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ProfileStore(Path(folder) / "profiles.json")
            profiles = [
                ProxyProfile(id="one", name="Endpoint One", listen_port=8666),
                ProxyProfile(id="two", name="Endpoint Two", listen_port=8667, transport_label="tls_passthrough"),
            ]
            store.save(profiles)
            loaded = store.load()
            self.assertEqual([p.id for p in loaded], ["one", "two"])
            self.assertEqual(loaded[1].transport_label, "tls_passthrough")

    def test_rejects_duplicate_listener_port(self):
        profiles = [
            ProxyProfile(id="one", name="Wildcard", bind_host="0.0.0.0", listen_port=8666),
            ProxyProfile(id="two", name="Loopback", bind_host="127.0.0.1", listen_port=8666),
        ]
        with self.assertRaisesRegex(ValueError, "collision"):
            ProfileStore._validate_unique(profiles)

    def test_import_merge_preserves_existing_profiles(self):
        current = [ProxyProfile(id="one", name="Existing", listen_port=8666)]
        incoming = [ProxyProfile(id="two", name="Imported", listen_port=8667)]
        merged = ProfileStore.import_profiles(current, incoming)
        self.assertEqual([p.id for p in merged], ["one", "two"])

    def test_import_rejects_duplicate_ids(self):
        current = [ProxyProfile(id="same", name="Existing", listen_port=8666)]
        incoming = [ProxyProfile(id="same", name="Imported", listen_port=8667)]
        with self.assertRaisesRegex(ValueError, "already exists"):
            ProfileStore.import_profiles(current, incoming)


if __name__ == "__main__":
    unittest.main()
