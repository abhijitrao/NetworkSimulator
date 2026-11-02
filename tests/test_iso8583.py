"""Tests for the POS ISO8583 stream framing and DE 3 extraction."""
import unittest

from simulator.proxy.iso8583 import (
    Iso8583FrameError,
    Iso8583StreamFramer,
    decode_bcd_length,
    extract_processing_code,
    extract_mti,
)


SAMPLE = bytes.fromhex(
    "014560009000010800202001000084010A96032100000100903633303030303237"
    "002330307C4646464646363030303030303030383030344244001684C6972FDA53F42"
    "C2D52ED95D261FA5A005034583939302020426F6E7573487562202030332E30322E"
    "30322E323530313133303030303030303030303030303030303030001730333037"
    "31343935362020202020203031"
)


class Iso8583ParserTests(unittest.TestCase):
    def test_sample_packet_has_bcd_length_and_processing_code(self):
        self.assertEqual(decode_bcd_length(SAMPLE[:2]), 145)
        self.assertEqual(len(SAMPLE) - 2, 145)
        self.assertEqual(extract_processing_code(SAMPLE), "960321")

    def test_mti_is_exposed_as_readable_digits(self):
        self.assertEqual(extract_mti(SAMPLE), "0800")

    def test_binary_length_header_and_processing_code(self):
        payload = bytes.fromhex("60009100010800202001000081008A982003") + bytes(220 - 18)
        frame = bytes.fromhex("00DC") + payload
        self.assertEqual(decode_bcd_length(frame[:2]), 220)
        self.assertEqual(len(frame) - 2, 220)
        self.assertEqual(extract_mti(frame), "0800")
        self.assertEqual(extract_processing_code(frame), "982003")
        self.assertEqual(Iso8583StreamFramer().feed(frame), [frame])

    def test_stream_framer_handles_fragmented_message(self):
        framer = Iso8583StreamFramer()
        self.assertEqual(framer.feed(SAMPLE[:11]), [])
        self.assertEqual(framer.pending_bytes, 11)
        self.assertEqual(framer.feed(SAMPLE[11:]), [SAMPLE])
        self.assertEqual(framer.pending_bytes, 0)

    def test_stream_framer_handles_multiple_messages_in_one_chunk(self):
        framer = Iso8583StreamFramer()
        self.assertEqual(framer.feed(SAMPLE + SAMPLE), [SAMPLE, SAMPLE])

    def test_missing_de3_returns_none(self):
        frame = bytearray(SAMPLE)
        frame[9] &= 0xDF
        self.assertIsNone(extract_processing_code(bytes(frame)))

    def test_invalid_bcd_length_rejected(self):
        with self.assertRaises(Iso8583FrameError):
            decode_bcd_length(bytes.fromhex("01FA"))


if __name__ == "__main__":
    unittest.main()
