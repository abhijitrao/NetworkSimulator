"""Integration tests for Processing Code-based request/response suppression."""
import socket
import socketserver
import threading
import unittest
import uuid

from simulator.models import FaultSettings, ProxyProfile
from simulator.proxy.manager import ProxyManager


SAMPLE = bytes.fromhex(
    "0145"  # 145 bytes follow the 2-byte length header.
    "60009000010800202001000084010A"  # TPDU, MTI, bitmap and following data
) + b"960321" + bytes.fromhex(
    "00000100903633303030303237"
    "002330307C4646464646363030303030303030383030344244001684C6972FDA53F42"
    "C2D52ED95D261FA5A005034583939302020426F6E7573487562202030332E30322E"
    "323530313133303030303030303030303030303030303030001730333037"
    "31343935362020202020203031"
)


class RecordingEchoHandler(socketserver.BaseRequestHandler):
    received = []
    received_event = threading.Event()

    def handle(self):
        self.request.settimeout(1)
        try:
            data = self.request.recv(65536)
            if data:
                self.received.append(data)
                self.received_event.set()
                self.request.sendall(data)
        except OSError:
            pass


class ProcessingCodeProxyTests(unittest.TestCase):
    def setUp(self):
        RecordingEchoHandler.received = []
        RecordingEchoHandler.received_event = threading.Event()

        class EchoServer(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self.server = EchoServer(("127.0.0.1", 0), RecordingEchoHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        listen_port = probe.getsockname()[1]
        probe.close()

        self.events = []
        self.raw_event = threading.Event()
        self.response_event = threading.Event()
        def record_event(event):
            self.events.append(event)
            if event.get('type') in {'RAW_REQUEST', 'RAW_RESPONSE'}:
                self.raw_event.set()
            if event.get('type') == 'RESPONSE':
                self.response_event.set()
        self.manager = ProxyManager(on_event=record_event)
        self.profile = ProxyProfile(
            id=str(uuid.uuid4()), name="DE3 test", upstream_host="127.0.0.1",
            upstream_port=self.server.server_address[1], bind_host="127.0.0.1",
            listen_port=listen_port, processing_codes=["960321"],
            fault_profile=FaultSettings(apply_to="response"),
        )
        self.manager.start(self.profile)

    def tearDown(self):
        self.manager.stop_all()
        self.server.shutdown()
        self.server.server_close()

    def test_response_rule_forwards_request_but_suppresses_reply(self):
        with socket.create_connection(("127.0.0.1", self.profile.listen_port), timeout=2) as client:
            client.settimeout(0.5)
            client.sendall(SAMPLE)
            self.assertTrue(RecordingEchoHandler.received_event.wait(1))
            self.assertEqual(RecordingEchoHandler.received[0], SAMPLE)
            with self.assertRaises(socket.timeout):
                client.recv(4096)
        self.assertFalse(any(e["type"] == "REQUEST_RECEIVED" for e in self.events))
        self.assertTrue(any(e["type"] == "REQUEST" and e["processing_code"] == "960321" for e in self.events))
        self.assertTrue(any(e["type"] == "DROPPED" and e["processing_code"] == "960321" for e in self.events))

    def test_raw_request_hex_is_emitted_only_when_enabled(self):
        # This test checks diagnostics only; disable the matching rule so the echo reply is not suppressed.
        self.manager.set_processing_codes(self.profile.id, [])
        self.manager.set_raw_hex_logging(True)
        with socket.create_connection(('127.0.0.1', self.profile.listen_port), timeout=2) as client:
            client.settimeout(2)
            client.sendall(SAMPLE)
            self.assertEqual(client.recv(len(SAMPLE)), SAMPLE)
            self.assertTrue(self.response_event.wait(2), 'Parsed RESPONSE event was not emitted')
            # Both directions should be captured when diagnostics are enabled.
            self.assertTrue(self.raw_event.wait(2), 'Raw HEX event was not emitted')
        raw_events = [e for e in self.events if e['type'] == 'RAW_REQUEST']
        self.assertTrue(raw_events)
        response_events = [e for e in self.events if e['type'] == 'RAW_RESPONSE']
        self.assertTrue(response_events, 'RAW_RESPONSE event was not emitted')
        self.assertTrue(any(e['type'] == 'REQUEST' and e['processing_code'] == '960321' for e in self.events))
        self.assertTrue(any(e['type'] == 'RESPONSE' and e['mti'] == '0800' and e['processing_code'] == '960321' for e in self.events))
        self.assertIn(SAMPLE[:16].hex().upper(), raw_events[0]['detail'])
        self.assertIn(SAMPLE[:16].hex().upper(), response_events[0]['detail'])

    def test_request_rule_does_not_forward_to_server(self):
        self.manager.set_fault(self.profile.id, FaultSettings(apply_to="request"))
        with socket.create_connection(("127.0.0.1", self.profile.listen_port), timeout=2) as client:
            client.settimeout(0.5)
            client.sendall(SAMPLE)
            with self.assertRaises(socket.timeout):
                client.recv(4096)
        self.assertFalse(RecordingEchoHandler.received_event.wait(0.2))
        self.assertTrue(any(e["type"] == "DROPPED" and e["processing_code"] == "960321" for e in self.events))


if __name__ == "__main__":
    unittest.main()
