"""Dashboard API tests with an isolated temporary configuration file."""
import tempfile
import unittest
from pathlib import Path

from app import create_app
from simulator.config_store import ProfileStore
from simulator.models import ProxyProfile


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Path(self.temp.name) / "profiles.json"
        ProfileStore(self.config).save([
            ProxyProfile(id="one", name="Test", listen_port=18766, bind_host="127.0.0.1")
        ])
        self.app = create_app(config_path=self.config)
        self.app.testing = True
        self.client = self.app.test_client()

    def tearDown(self):
        self.app.extensions["proxy_manager"].stop_all()
        self.temp.cleanup()

    def test_state_returns_profiles(self):
        response = self.client.get("/api/state")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["profiles"][0]["id"], "one")

    def test_create_and_delete_profile(self):
        created = self.client.post("/api/profiles", json={
            "id": "two", "name": "Second", "upstream_host": "127.0.0.1",
            "upstream_port": 9001, "bind_host": "127.0.0.1", "listen_port": 18767,
            "transport_label": "tcp", "enabled": False,
        })
        self.assertEqual(created.status_code, 201)
        deleted = self.client.delete("/api/profiles/two")
        self.assertEqual(deleted.status_code, 200)

    def test_import_merge(self):
        response = self.client.post("/api/profiles/import", json=[{
            "id": "two", "name": "Imported", "upstream_host": "127.0.0.1",
            "upstream_port": 9002, "bind_host": "127.0.0.1", "listen_port": 18768,
            "enabled": False,
        }])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["total"], 2)

    def test_reject_remote_client(self):
        response = self.client.get("/api/state", environ_overrides={"REMOTE_ADDR": "192.0.2.1"})
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
