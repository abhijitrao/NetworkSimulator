"""Minimal stream framer for the simulator's ISO8583 TCP wire format.

Frame: 2-byte packed-BCD length (bytes after header), 5-byte TPDU,
2-byte MTI, 8-byte primary bitmap, followed by data elements.
Only DE 3 is decoded; the remaining fields are deliberately opaque.
"""
from __future__ import annotations


class Iso8583FrameError(ValueError):
    pass


def decode_bcd_length(header: bytes) -> int:
    if len(header) != 2:
        raise Iso8583FrameError("Length header must contain exactly 2 bytes")
    digits = []
    for byte in header:
        for nibble in (byte >> 4, byte & 0x0F):
            if nibble > 9:
                raise Iso8583FrameError("Invalid packed-BCD length header")
            digits.append(str(nibble))
    return int("".join(digits))


def extract_processing_code(frame: bytes) -> str | None:
    """Return DE 3 as six decimal digits, or None when bitmap says absent."""
    if len(frame) < 19:
        raise Iso8583FrameError("ISO8583 frame is too short for TPDU, MTI and bitmap")
    declared = decode_bcd_length(frame[:2])
    if declared != len(frame) - 2:
        raise Iso8583FrameError("Frame length does not match its BCD header")
    bitmap = frame[9:17]
    # Bit 1 in the primary bitmap indicates a secondary bitmap.
    if bitmap[0] & 0x80:
        raise Iso8583FrameError("Secondary bitmap is not supported by this request format")
    # DE 3 is bitmap bit 3 (MSB-first numbering).
    if not (bitmap[0] & 0x20):
        return None
    raw = frame[17:20]
    if len(raw) != 3:
        raise Iso8583FrameError("DE 3 is incomplete")
    digits = []
    for byte in raw:
        for nibble in (byte >> 4, byte & 0x0F):
            if nibble > 9:
                raise Iso8583FrameError("DE 3 is not packed BCD")
            digits.append(str(nibble))
    return "".join(digits)


class Iso8583StreamFramer:
    """Collect arbitrary TCP chunks and emit complete length-prefixed frames."""
    def __init__(self, max_frame_length: int = 65535):
        self._buffer = bytearray()
        self.max_frame_length = max_frame_length

    def feed(self, chunk: bytes) -> list[bytes]:
        self._buffer.extend(chunk)
        frames = []
        while len(self._buffer) >= 2:
            length = decode_bcd_length(self._buffer[:2])
            if length < 15 or length > self.max_frame_length:
                raise Iso8583FrameError(f"Invalid ISO8583 frame length: {length}")
            total = 2 + length
            if len(self._buffer) < total:
                break
            frames.append(bytes(self._buffer[:total]))
            del self._buffer[:total]
        return frames

    @property
    def pending_bytes(self) -> int:
        return len(self._buffer)
