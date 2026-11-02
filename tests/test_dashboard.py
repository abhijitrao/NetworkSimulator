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

    def test_dashboard_page_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Network Simulator", response.data)

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

    def test_processing_codes_are_saved_for_plain_tcp_profile(self):
        response = self.client.post("/api/profiles/one/processing-codes", json={
            "processing_codes": ["960321", "000000", "960321"], "apply_to": "response"
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["processing_codes"], ["960321", "000000"])
        saved = ProfileStore(self.config).load()[0]
        self.assertEqual(saved.processing_codes, ["960321", "000000"])
        self.assertEqual(saved.fault_profile.apply_to, "response")

    def test_processing_codes_reject_invalid_values(self):
        response = self.client.post("/api/profiles/one/processing-codes", json={
            "processing_codes": ["96321", "ABCDEF"]
        })
        self.assertEqual(response.status_code, 400)

    def test_profile_raw_hex_setting_is_persisted(self):
        response = self.client.put("/api/profiles/one", json={
            "name": "Test", "upstream_host": "127.0.0.1", "upstream_port": 9000,
            "bind_host": "127.0.0.1", "listen_port": 18766, "transport_label": "tcp",
            "enabled": True, "raw_hex_logging": True,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.client.get("/api/state").json["profiles"][0]["raw_hex_logging"])

    def test_raw_hex_capture_is_opt_in_and_disable_clears_raw_events(self):
        initial = self.client.get('/api/diagnostics/raw-hex')
        self.assertFalse(initial.json['enabled'])
        enabled = self.client.post('/api/diagnostics/raw-hex', json={'enabled': True})
        self.assertEqual(enabled.status_code, 200)
        self.assertTrue(enabled.json['enabled'])
        self.app.extensions['proxy_manager'].on_event({'timestamp': 1, 'type': 'RAW_REQUEST'})
        self.app.extensions['proxy_manager'].on_event({'timestamp': 2, 'type': 'RAW_RESPONSE'})
        disabled = self.client.post('/api/diagnostics/raw-hex', json={'enabled': False})
        self.assertEqual(disabled.status_code, 200)
        self.assertFalse(any(e['type'] in {'RAW_REQUEST', 'RAW_RESPONSE'} for e in self.client.get('/api/events').json['events']))

    def test_reject_remote_client(self):
        response = self.client.get("/api/state", environ_overrides={"REMOTE_ADDR": "192.0.2.1"})
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
