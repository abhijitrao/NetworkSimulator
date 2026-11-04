"""Tests for the POS ISO8583 stream framing and DE 3 extraction."""
import unittest

from simulator.proxy.iso8583 import (
    Iso8583FrameError,
    Iso8583StreamFramer,
    decode_frame_length,
    extract_processing_code,
    extract_mti,
)


SAMPLE = bytes.fromhex(
    "009160009000010800202001000084010A96032100000100903633303030303237"
    "002330307C4646464646363030303030303030383030344244001684C6972FDA53F42"
    "C2D52ED95D261FA5A005034583939302020426F6E7573487562202030332E30322E"
    "30322E323530313133303030303030303030303030303030303030001730333037"
    "31343935362020202020203031"
)


class Iso8583ParserTests(unittest.TestCase):
    def test_sample_packet_with_ascii_processing_code(self):
        # Replace the sample's three packed bytes with six ASCII digits.
        frame = SAMPLE[:17] + b"960321" + SAMPLE[20:]
        frame = bytes.fromhex("0094") + frame[2:]
        self.assertEqual(decode_frame_length(frame[:2]), 148)
        self.assertEqual(len(frame) - 2, 148)
        self.assertEqual(extract_processing_code(frame), "960321")

    def test_mti_is_exposed_as_readable_digits(self):
        self.assertEqual(extract_mti(SAMPLE), "0800")

    def test_packed_bcd_processing_code_from_live_pos_packet(self):
        frame = bytes.fromhex(
            "00DD60009100010800202001000081008A982003001401"
            "00913633303030313231008334353031377E323631313032313633363436"
            "7E3236313130323136333335307E323631313032313633363436"
            "7E3236313130323136333634367E7E3130307E333539333434313430323534323031"
            "7E7E7E7E7E003231355E315E30322D4E6F762D323032365E30322D4E6F762D32303236"
            "5E305E30005034413931305320426F6E7573487562202030332E30342E30312E"
            "32363130323830303030303330383730303030303030303000173238343030313032373520202020203031"
        )
        self.assertEqual(decode_frame_length(frame[:2]), 221)
        self.assertEqual(len(frame) - 2, 221)
        self.assertEqual(extract_mti(frame), "0800")
        self.assertEqual(extract_processing_code(frame), "982003")

    def test_binary_length_header_and_processing_code(self):
        payload = bytes.fromhex("60009100010800202001000081008A") + b"982003" + bytes(220 - 21)
        frame = bytes.fromhex("00DC") + payload
        self.assertEqual(decode_frame_length(frame[:2]), 220)
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

    def test_non_ascii_de3_is_rejected(self):
        frame = bytearray(bytes.fromhex("00DC60009100010800202001000081008A") + b"982003" + bytes(220 - 23))
        frame[17] = 0x98
        with self.assertRaises(Iso8583FrameError):
            extract_processing_code(bytes(frame))

    def test_non_decimal_length_header_uses_binary_value(self):
        self.assertEqual(decode_frame_length(bytes.fromhex("01FA")), 506)


if __name__ == "__main__":
    unittest.main()
