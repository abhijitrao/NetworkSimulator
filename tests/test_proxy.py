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
        self.manager = ProxyManager()
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


if __name__ == "__main__":
    unittest.main()
