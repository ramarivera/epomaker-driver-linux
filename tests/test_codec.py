import random

import pytest

from epomaker_driver import codec
from epomaker_driver.errors import ProtocolError, UnsupportedDevice
from epomaker_driver.models import glyph_matrix, model_by_id


def test_random_header_checksums_leave_payload_untouched():
    random_source = random.Random(3059)
    for checksum in (7, 8):
        for _ in range(100):
            raw = bytes(random_source.randrange(256) for _ in range(64))
            encoded = codec.packet(raw, checksum)
            assert sum(encoded[: checksum + 1]) & 255 == 255
            assert encoded[checksum + 1 :] == raw[checksum + 1 :]
    assert codec.packet(bytes(64), None) == bytes(64)


@pytest.mark.parametrize(
    "make",
    [
        lambda: codec.packet([1], 6),
        lambda: codec.bluetooth_report(b"x"),
        lambda: codec.usb_report(b"x"),
        lambda: codec.single_key(0, 0, [0, 1]),
        lambda: codec.fn_single(0, [0, 1]),
        lambda: codec.light("invalid"),
        lambda: codec.matrix_chunks(b"x").__next__(),
        lambda: codec.macro_data(1, [{"hid_usage": 4, "down": True, "delay_ms": 1}] * 128),
        lambda: list(codec.macro_chunks(0, b"x")),
        lambda: list(codec.picture_chunks(b"x")),
        lambda: codec.macro_keyboard_event(0, True, 1),
        lambda: codec.screen_prepare(4, (1, 2, 3)),
        lambda: codec.screen_prepare(4, (0, 0, 1, 1), frames=0),
        lambda: list(codec.screen_chunks(b"", frames=1)),
        lambda: codec.rgb565_column_major([]),
        lambda: codec.rgb565_column_major([[]]),
    ],
)
def test_input_limits(make):
    with pytest.raises(ValueError):
        make()


def test_lighting_all_capabilities_and_wire_details():
    for mode in codec.LIGHT_MODES:
        p = codec.light(mode, rgb=0x123456, rainbow=True)
        assert p[0] == 7
        assert p[1] == codec.LIGHT_MODES[mode]
        response = bytearray(p)
        response[0] = 0x87
        assert codec.parse_light(response)["mode"] == mode
    for mode in codec.SIDE_MODES:
        p = codec.light(mode, side=True, speed=3)
        assert p[2] == 3
    assert codec.light("picture", option=4)[5:8] == bytes([0, 200, 200])
    assert codec.light("music")[4] == 4
    assert codec.light("screen")[4] == 0
    assert codec.light("neon", side=True)[4] == 8
    raw = bytearray(64)
    raw[0] = 0x87
    raw[1] = 200
    raw[4] = 3
    assert codec.parse_light(raw)["mode"] == "unknown"
    assert codec.parse_light(raw)["rgb"] == 0x00FF00
    for function in (codec.parse_light, codec.parse_sleep):
        with pytest.raises(ProtocolError):
            function(bytes(64))


def test_macro_hole_and_last_partial_chunk():
    data = bytearray(256)
    data[0] = 1
    data[255] = 7
    chunks = list(codec.macro_chunks(3, data))
    assert len(chunks) == 5
    assert chunks[4][2] == 4
    assert chunks[4][4] == 1
    assert chunks[4][39] == 7
    assert chunks[4][40:] == bytes(24)
    assert len(list(codec.macro_chunks(0, bytes(256)))) == 1


def test_model_resolution():
    assert model_by_id(3059)["displayName"] == "Epomaker Glyph"
    with pytest.raises(UnsupportedDevice):
        model_by_id(999999)
    with pytest.raises(ValueError):
        glyph_matrix("nonexistent")


def test_picture_shape():
    chunks = list(codec.picture_chunks(bytes([255]) * 378, picture=4))
    assert len(chunks) == 7
    assert chunks[-1][4:6] == bytes([42, 1])
    assert chunks[-1][50:] == bytes(14)


@pytest.mark.parametrize("bank", range(5))
def test_still_bank_wire_header(bank):
    # Vendor ___pngToDevice sends frameNum=1 and currentFrame=selected bank.
    prepare = codec.screen_prepare(2, (0, 0, 1, 1), frame=bank)
    chunk = next(codec.screen_chunks(bytes.fromhex("f800"), frame=bank))
    assert prepare[:8] == bytes([0xA5, bank, 1, 0, 2, 0, 0, 0x57 - bank])
    assert chunk[:8] == bytes([0x25, bank, 1, 0, 0, 0, 2, 0xD7 - bank])
    assert chunk[8:10] == bytes.fromhex("f800")


@pytest.mark.parametrize("frame,frames", [(5, 1), (2, 2), (0, 0), (-1, 1), (True, 1)])
def test_display_bank_and_animation_limits(frame, frames):
    with pytest.raises(ValueError):
        codec.screen_prepare(2, (0, 0, 1, 1), frame=frame, frames=frames)
    with pytest.raises(ValueError):
        list(codec.screen_chunks(b"xx", frame=frame, frames=frames))


def test_rgb24_conversion_and_metadata_errors():
    assert codec.rgb24_column_major([[0x123456, 0xABCDEF], [0x010203, 0x040506]]) == bytes.fromhex(
        "123456010203abcdef040506"
    )
    for rows in [[], [[]], [[1], [2, 3]], [[0x1000000]]]:
        with pytest.raises(ValueError):
            codec.rgb24_column_major(rows)
    with pytest.raises(ValueError):
        codec.screen_prepare(3, (0, 0, 1, 1), rgb_bits=32)
    with pytest.raises(ValueError):
        list(codec.screen_chunks(bytes(3), rgb_bits=32))
