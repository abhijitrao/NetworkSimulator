"""Integration coverage for live fault injection on an echo upstream."""
import socket
import socketserver
import threading
import time
import unittest
import uuid

from simulator.models import FaultSettings, ProxyProfile
from simulator.proxy.manager import ProxyManager


class EchoHandler(socketserver.BaseRequestHandler):
    def handle(self):
        while True:
            data = self.request.recv(4096)
            if not data:
                return
            self.request.sendall(data)


class FaultInjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class EchoServer(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True
        cls.echo = EchoServer(("127.0.0.1", 0), EchoHandler)
        threading.Thread(target=cls.echo.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.echo.shutdown()
        cls.echo.server_close()

    def setUp(self):
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        self.manager = ProxyManager()
        self.profile = ProxyProfile(
            id=str(uuid.uuid4()), name="fault-test", upstream_host="127.0.0.1",
            upstream_port=self.echo.server_address[1], bind_host="127.0.0.1", listen_port=port,
        )
        self.manager.start(self.profile)
        self.port = port

    def tearDown(self):
        self.manager.stop_all()

    def test_pause_response_and_resume_without_reconnect(self):
        with socket.create_connection(("127.0.0.1", self.port), timeout=2) as client:
            client.settimeout(0.25)
            self.manager.set_fault(self.profile.id, FaultSettings(pause_upstream_to_client=True))
            client.sendall(b"held-response")
            with self.assertRaises(socket.timeout):
                client.recv(64)
            self.manager.set_fault(self.profile.id, FaultSettings())
            client.settimeout(2)
            self.assertEqual(client.recv(64), b"held-response")

    def test_live_latency_is_applied(self):
        self.manager.set_fault(self.profile.id, FaultSettings(latency_ms=120))
        started = time.monotonic()
        with socket.create_connection(("127.0.0.1", self.port), timeout=2) as client:
            client.sendall(b"latency")
            self.assertEqual(client.recv(32), b"latency")
        self.assertGreaterEqual(time.monotonic() - started, 0.10)


if __name__ == "__main__":
    unittest.main()
