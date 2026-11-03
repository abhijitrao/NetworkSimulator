"""Integration tests for the core TCP relay; uses only the Python standard library."""
import socket
import socketserver
import threading
import unittest
import uuid

from simulator.models import ProxyProfile
from simulator.proxy.manager import ProxyManager


class EchoHandler(socketserver.BaseRequestHandler):
    def handle(self):
        while True:
            data = self.request.recv(4096)
            if not data:
                return
            self.request.sendall(data)


class ProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class EchoServer(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True
        cls.echo = EchoServer(("127.0.0.1", 0), EchoHandler)
        cls.echo_thread = threading.Thread(target=cls.echo.serve_forever, daemon=True)
        cls.echo_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.echo.shutdown()
        cls.echo.server_close()

    def setUp(self):
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        self.listen_port = probe.getsockname()[1]
        probe.close()
        self.events = []
        self.events_lock = threading.Lock()

        def record_event(event):
            with self.events_lock:
                self.events.append(event)

        self.manager = ProxyManager(on_event=record_event)
        self.profile = ProxyProfile(
            id=str(uuid.uuid4()), name="test", upstream_host="127.0.0.1",
            upstream_port=self.echo.server_address[1], bind_host="127.0.0.1",
            listen_port=self.listen_port,
        )
        self.manager.start(self.profile)

    def tearDown(self):
        self.manager.stop_all()

    def test_bidirectional_echo(self):
        payload = b"POS simulator test payload\x00\xff"
        with socket.create_connection(("127.0.0.1", self.listen_port), timeout=2) as client:
            client.sendall(payload)
            self.assertEqual(client.recv(len(payload)), payload)

    def test_multiple_profiles_run_independently(self):
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        second_port = probe.getsockname()[1]
        probe.close()
        second = ProxyProfile(
            id=str(uuid.uuid4()), name="second", upstream_host="127.0.0.1",
            upstream_port=self.echo.server_address[1], bind_host="127.0.0.1", listen_port=second_port,
        )
        self.manager.start(second)
        for port, payload in ((self.listen_port, b"profile-one"), (second_port, b"profile-two")):
            with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
                client.sendall(payload)
                self.assertEqual(client.recv(128), payload)
        self.assertEqual(len(self.manager.status()), 2)

    def test_multiple_clients(self):
        messages = [f"client-{i}".encode() for i in range(8)]
        results = []
        def run(message):
            with socket.create_connection(("127.0.0.1", self.listen_port), timeout=2) as client:
                client.sendall(message)
                results.append(client.recv(128))
        workers = [threading.Thread(target=run, args=(message,)) for message in messages]
        for worker in workers: worker.start()
        for worker in workers: worker.join(timeout=3)
        self.assertCountEqual(results, messages)


    def test_tls_passthrough_logs_encrypted_request_response_and_optional_hex(self):
        self.manager.stop_all()
        self.profile.transport_label = "tls_passthrough"
        self.manager = ProxyManager(on_event=self.manager.on_event)
        self.manager.start(self.profile)
        self.manager.set_raw_hex_logging(True)

        payload = b"\\x16\\x03\\x03\\x00\\x05HELLO"
        with socket.create_connection(("127.0.0.1", self.listen_port), timeout=2) as client:
            client.sendall(payload)
            self.assertEqual(client.recv(len(payload)), payload)

        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with self.events_lock:
                types = [event["type"] for event in self.events]
            if "REQUEST" in types and "RESPONSE" in types:
                break
            time.sleep(0.01)

        with self.events_lock:
            events = list(self.events)
        request = next(event for event in events if event["type"] == "REQUEST")
        response = next(event for event in events if event["type"] == "RESPONSE")
        raw_request = next(event for event in events if event["type"] == "RAW_REQUEST")
        raw_response = next(event for event in events if event["type"] == "RAW_RESPONSE")
        self.assertEqual(request["mti"], "TLS")
        self.assertEqual(response["mti"], "TLS")
        self.assertIn("8 bytes", request["detail"])
        self.assertIn("8 bytes", response["detail"])
        self.assertIn(payload.hex().upper(), raw_request["detail"])
        self.assertIn(payload.hex().upper(), raw_response["detail"])

    def test_tls_passthrough_logs_transfer_metadata_without_raw_hex_by_default(self):
        self.manager.stop_all()
        self.profile.transport_label = "tls_passthrough"
        self.manager = ProxyManager(on_event=self.manager.on_event)
        self.manager.start(self.profile)

        payload = b"\\x17\\x03\\x03\\x00\\x04DATA"
        with socket.create_connection(("127.0.0.1", self.listen_port), timeout=2) as client:
            client.sendall(payload)
            self.assertEqual(client.recv(len(payload)), payload)

        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with self.events_lock:
                types = [event["type"] for event in self.events]
            if "REQUEST" in types and "RESPONSE" in types:
                break
            time.sleep(0.01)

        with self.events_lock:
            events = list(self.events)
        self.assertTrue(any(event["type"] == "REQUEST" and event["mti"] == "TLS" for event in events))
        self.assertTrue(any(event["type"] == "RESPONSE" and event["mti"] == "TLS" for event in events))
        self.assertFalse(any(event["type"] in {"RAW_REQUEST", "RAW_RESPONSE"} for event in events))


if __name__ == "__main__":
    unittest.main()
