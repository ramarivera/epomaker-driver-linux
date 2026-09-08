"""Compare offline examples to vendor-derived vectors; never opens a device.
Evidence: exports/20260908-epomaker-linux-research/tools/make-golden-vectors.mjs.
"""

import json
import unittest
from pathlib import Path

from epomaker_driver import codec

V = json.loads((Path(__file__).parent / "fixtures/glyph-packets.json").read_text())


class CodecTests(unittest.TestCase):
    def test_identity(self):
        p = codec.identify_request()
        self.assertEqual(p, bytes(V["identity"]))
        self.assertEqual(sum(p[:8]) & 255, 255)
        self.assertEqual(len(codec.usb_report(p)), 65)
        self.assertEqual(codec.usb_report(p)[:2], b"\x00\x8f")
        self.assertEqual(len(codec.bluetooth_report(p)), 66)
        self.assertEqual(codec.bluetooth_report(p)[:3], b"\x06\x55\x8f")

    def test_single_key(self):
        self.assertEqual(codec.single_key(0, 9, [0, 0, 5, 0]), bytes(V["single_key"]))

    def test_sleep(self):
        self.assertEqual(codec.sleep_times(120, 240, 1800, 3600), bytes(V["sleep"]))

    def test_rgb_checksum_and_white_substitution(self):
        p = codec.solid_light(0xFFFFFF)
        self.assertEqual(p, bytes(V["solid_white"]))
        self.assertEqual(p[5:8], bytes([250, 255, 250]))
        self.assertEqual(sum(p[:9]) & 255, 255)

    def test_screen_handshake_split_length_and_coordinates(self):
        p = codec.screen_prepare(121552, (0, 0, 428, 142), delay=10)
        self.assertEqual(p, bytes(V["screen_prepare"]))
        self.assertEqual(p[10], 172)
        self.assertEqual(p[14], 1)
        self.assertEqual(p[16], 1)

    def test_screen_chunk_boundary(self):
        chunks = list(codec.screen_chunks(bytes(range(58)), delay=10))
        self.assertEqual(chunks, [bytes(p) for p in V["screen_chunks"]])
        self.assertEqual(chunks[1][6], 2)
        self.assertEqual(chunks[1][10:], bytes(54))

    def test_rgb565_column_order(self):
        # Two rows: red green / blue white => column order red blue green white.
        self.assertEqual(
            codec.rgb565_column_major([[0xFF0000, 0x00FF00], [0x0000FF, 0xFFFFFF]]),
            bytes.fromhex("f800 001f 07e0 ffff"),
        )

    def test_macro_compact_and_long_delays(self):
        self.assertEqual(codec.macro_keyboard_event(4, True, 127), bytes.fromhex("04ff"))
        self.assertEqual(codec.macro_keyboard_event(4, False, 128), bytes.fromhex("04008000"))

    def test_identity_decode(self):
        p = bytes.fromhex("8ff30b000000000004000001")
        self.assertEqual(
            codec.parse_identity(p),
            {"device_id": 3059, "usb_version": 1024, "is_boot": False, "light_sync": True},
        )

    def test_clock_endianness(self):
        p = codec.clock_command(2026, 9, 8, 14, 30, 59)
        self.assertEqual(p[8:15], bytes.fromhex("07ea09080e1e3b"))

    def test_reject_invalid_inputs(self):
        for call in [
            lambda: codec.single_key(3, 0, [0] * 4),
            lambda: codec.single_key(0, 128, [0] * 4),
            lambda: codec.packet(bytes(65)),
            lambda: codec.sleep_times(70000, 0, 0, 0),
            lambda: codec.rgb565_column_major([[0], [0, 1]]),
            lambda: codec.macro_keyboard_event(4, True, 0),
            lambda: codec.screen_prepare(10, (0, 0, 429, 142)),
            lambda: codec.usb_report(bytes(63)),
            lambda: codec.parse_identity(bytes(64)),
        ]:
            with self.assertRaises(ValueError):
                call()


if __name__ == "__main__":
    unittest.main()
