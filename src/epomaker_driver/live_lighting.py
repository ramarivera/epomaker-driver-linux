"""Glyph host-driven RGB frame encoding.

The vendor host sends exactly 378 RGB bytes as seven 64-byte HID commands.
See ``docs/releases/glyph-live-light-audit.md`` for the captured framing.
"""

from __future__ import annotations

from . import codec

FRAME_BYTES = 378
CHUNK_BYTES = 56
HEADER_BYTES = 8
PACKET_COUNT = (FRAME_BYTES + CHUNK_BYTES - 1) // CHUNK_BYTES


def frame_packets(colors) -> tuple[bytes, ...]:
    """Encode one complete Glyph live-light frame without performing I/O."""

    if not isinstance(colors, (bytes, bytearray, memoryview)):
        raise TypeError("live-light frame must be a bytes-like RGB buffer")
    colors = bytes(colors)
    if len(colors) != FRAME_BYTES:
        raise ValueError(f"live-light frame must contain exactly {FRAME_BYTES} RGB bytes")

    packets = []
    for page in range(PACKET_COUNT):
        chunk = colors[page * CHUNK_BYTES : (page + 1) * CHUNK_BYTES]
        payload = bytes((0x0F, 1, page, CHUNK_BYTES, int(page == PACKET_COUNT - 1))) + bytes(3)
        payload += chunk + bytes(CHUNK_BYTES - len(chunk))
        packets.append(codec.packet(payload))
    return tuple(packets)
