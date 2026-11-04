"""Integration tests for Processing Code-based request/response suppression."""
import socket
import socketserver
import threading
import time
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
    fragment_response = False

    def handle(self):
        self.request.settimeout(1)
        try:
            data = self.request.recv(65536)
            if data:
                self.received.append(data)
                self.received_event.set()
                if self.fragment_response and len(data) > 10:
                    self.request.sendall(data[:10])
                    time.sleep(0.05)
                    self.request.sendall(data[10:])
                else:
                    self.request.sendall(data)
        except OSError:
            pass


class ProcessingCodeProxyTests(unittest.TestCase):
    def setUp(self):
        RecordingEchoHandler.received = []
        RecordingEchoHandler.received_event = threading.Event()
        RecordingEchoHandler.fragment_response = False

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


    def test_block_rule_does_not_forward_request(self):
        self.manager.set_processing_code_rules(self.profile.id, {
            "960321": {"action": "block", "response_hex": ""}
        })
        with socket.create_connection(("127.0.0.1", self.profile.listen_port), timeout=2) as client:
            client.settimeout(0.4)
            client.sendall(SAMPLE)
            with self.assertRaises(socket.timeout):
                client.recv(4096)
        self.assertFalse(RecordingEchoHandler.received_event.wait(0.2))
        self.assertTrue(any(e["type"] == "DROPPED" and e["processing_code"] == "960321" for e in self.events))

    def test_block_rule_does_not_break_unmatched_api_with_fragmented_host_response(self):
        # 960321 is blocked, but a different Processing Code must still pass through.
        self.manager.set_processing_code_rules(self.profile.id, {
            "960321": {"action": "block", "response_hex": ""}
        })
        RecordingEchoHandler.fragment_response = True
        unmatched_request = SAMPLE[:17] + b"982002" + SAMPLE[23:]

        with socket.create_connection(("127.0.0.1", self.profile.listen_port), timeout=2) as client:
            client.settimeout(2)
            client.sendall(unmatched_request)
            received = bytearray()
            while len(received) < len(unmatched_request):
                part = client.recv(len(unmatched_request) - len(received))
                self.assertTrue(part, "Proxy closed before the complete host response arrived")
                received.extend(part)

        self.assertEqual(bytes(received), unmatched_request)
        self.assertEqual(RecordingEchoHandler.received[-1], unmatched_request)
        self.assertTrue(any(
            event["type"] == "REQUEST" and event["processing_code"] == "982002"
            for event in self.events
        ))

    def test_alter_response_rule_replaces_server_frame(self):
        replacement = bytearray(SAMPLE)
        replacement[7:9] = bytes.fromhex("0810")  # 0810 response MTI
        replacement_bytes = bytes(replacement)
        self.manager.set_processing_code_rules(self.profile.id, {
            "960321": {"action": "alter_response", "response_hex": replacement_bytes.hex().upper()}
        })
        with socket.create_connection(("127.0.0.1", self.profile.listen_port), timeout=2) as client:
            client.settimeout(2)
            client.sendall(SAMPLE)
            self.assertEqual(client.recv(len(replacement_bytes)), replacement_bytes)
        self.assertTrue(any(e["type"] == "RESPONSE_REPLACED" and e["processing_code"] == "960321" for e in self.events))

    def test_no_action_rule_forwards_original_request_and_response(self):
        self.manager.set_processing_code_rules(self.profile.id, {
            "960321": {"action": "none", "response_hex": ""}
        })
        with socket.create_connection(("127.0.0.1", self.profile.listen_port), timeout=2) as client:
            client.settimeout(2)
            client.sendall(SAMPLE)
            self.assertEqual(client.recv(len(SAMPLE)), SAMPLE)
        self.assertTrue(any(e["type"] == "MATCHED" and "No Action" in e["detail"] for e in self.events))

    def test_profile_request_sequence_blocks_selected_connection_responses(self):
        self.manager.set_processing_codes(self.profile.id, [])
        self.manager.configure_request_sequence_fault(self.profile.id, True, [2, 3, 5])
        tls_profile = ProxyProfile.from_dict({
            **self.profile.to_dict(),
            "id": str(uuid.uuid4()),
            "name": "TLS sequence test",
            "listen_port": self.profile.listen_port + 1,
            "transport_label": "tls_passthrough",
            "processing_codes": [],
        })
        self.manager.start(tls_profile)

        # Request 1 on TCP is forwarded and its echo response reaches the POS.
        with socket.create_connection(("127.0.0.1", self.profile.listen_port), timeout=2) as first:
            first.settimeout(2)
            first.sendall(SAMPLE)
            self.assertEqual(first.recv(len(SAMPLE)), SAMPLE)
        self.assertEqual(self.manager.request_sequence_status(self.profile.id)["counter"], 1)

        # Request 2 is still forwarded to the host, but its response is not returned.
        RecordingEchoHandler.received_event.clear()
        with socket.create_connection(("127.0.0.1", self.profile.listen_port), timeout=2) as second:
            second.settimeout(0.4)
            second.sendall(SAMPLE)
            self.assertTrue(RecordingEchoHandler.received_event.wait(1))
            with self.assertRaises(socket.timeout):
                second.recv(4096)

        self.assertEqual(len(RecordingEchoHandler.received), 2)
        self.assertEqual(self.manager.request_sequence_status(self.profile.id)["counter"], 2)
        self.assertTrue(any(e["type"] == "SEQUENCE_BLOCKED" and "Request #2" in e["detail"] for e in self.events))

    def test_sequence_reset_and_order_change_restart_counter(self):
        self.manager.configure_request_sequence_fault(self.profile.id, True, [2, 3, 5])
        self.assertEqual(self.manager._on_request_accepted(self.profile.id), (1, False))
        self.assertEqual(self.manager._on_request_accepted(self.profile.id), (2, True))
        self.assertEqual(self.manager.reset_request_sequence_fault(self.profile.id)["counter"], 0)
        self.assertEqual(self.manager._on_request_accepted(self.profile.id), (1, False))
        status = self.manager.configure_request_sequence_fault(self.profile.id, True, [4])
        self.assertEqual(status["counter"], 0)
        self.assertEqual(self.manager._on_request_accepted(self.profile.id), (1, False))
        self.assertEqual(self.manager.configure_request_sequence_fault(self.profile.id, False, [4])["counter"], 0)
        self.assertIsNone(self.manager._on_request_accepted(self.profile.id))

    def test_sequence_counters_are_independent_per_profile(self):
        second_id = str(uuid.uuid4())
        self.manager.configure_request_sequence_fault(self.profile.id, True, [2])
        self.manager.configure_request_sequence_fault(second_id, True, [1])

        self.assertEqual(self.manager._on_request_accepted(self.profile.id), (1, False))
        self.assertEqual(self.manager._on_request_accepted(second_id), (1, True))
        self.assertEqual(self.manager._on_request_accepted(self.profile.id), (2, True))
        self.assertEqual(self.manager.request_sequence_status(self.profile.id)["counter"], 2)
        self.assertEqual(self.manager.request_sequence_status(second_id)["counter"], 1)

if __name__ == "__main__":
    unittest.main()
