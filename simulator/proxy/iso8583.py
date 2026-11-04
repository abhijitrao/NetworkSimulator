"""Minimal stream framer for the simulator's ISO8583 TCP wire format.

Frame: 2-byte big-endian HEX length (bytes after header), 5-byte TPDU,
2-byte MTI, 8-byte primary bitmap, followed by data elements.
Only DE 3 is decoded; the remaining fields are deliberately opaque.
"""
from __future__ import annotations


class Iso8583FrameError(ValueError):
    pass


def decode_frame_length(header: bytes) -> int:
    """Decode the 2-byte frame length as an unsigned big-endian HEX value."""
    if len(header) != 2:
        raise Iso8583FrameError("Length header must contain exactly 2 bytes")
    return int.from_bytes(header, byteorder="big", signed=False)


def extract_mti(frame: bytes) -> str:
    """Return the four-digit MTI as readable decimal text."""
    if len(frame) < 9:
        raise Iso8583FrameError("ISO8583 frame is too short for MTI")
    digits = []
    for byte in frame[7:9]:
        for nibble in (byte >> 4, byte & 0x0F):
            if nibble > 9:
                raise Iso8583FrameError("MTI is not packed BCD")
            digits.append(str(nibble))
    return "".join(digits)


def extract_processing_code(frame: bytes) -> str | None:
    """Return DE 3 as six digits, supporting ASCII and packed-BCD wire formats."""
    if len(frame) < 20:
        raise Iso8583FrameError("ISO8583 frame is too short for DE 3")
    declared = decode_frame_length(frame[:2])
    if declared != len(frame) - 2:
        raise Iso8583FrameError("Frame length does not match its header")
    bitmap = frame[9:17]
    if bitmap[0] & 0x80:
        raise Iso8583FrameError("Secondary bitmap is not supported by this request format")
    if not (bitmap[0] & 0x20):
        return None

    # Prefer the six-byte ASCII representation when present.
    ascii_raw = frame[17:23]
    if len(ascii_raw) == 6 and all(0x30 <= value <= 0x39 for value in ascii_raw):
        return ascii_raw.decode("ascii")

    # POS terminals may encode DE 3 as three packed-BCD bytes (e.g. 98 20 03).
    bcd_raw = frame[17:20]
    digits = []
    for value in bcd_raw:
        high, low = value >> 4, value & 0x0F
        if high > 9 or low > 9:
            raise Iso8583FrameError("DE 3 is neither six ASCII digits nor packed BCD")
        digits.extend((str(high), str(low)))
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
            length = decode_frame_length(self._buffer[:2])
            if length < 15 or length > self.max_frame_length:
                raise Iso8583FrameError(f"Invalid ISO8583 frame length: {length}")
            total = 2 + length
            if len(self._buffer) < total:
                break
            frames.append(bytes(self._buffer[:total]))
            del self._buffer[:total]
        return frames

    def take_pending(self) -> bytes:
        pending = bytes(self._buffer)
        self._buffer.clear()
        return pending

    @property
    def pending_bytes(self) -> int:
        return len(self._buffer)
