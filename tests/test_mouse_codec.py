import pytest

from epomaker_driver import codec
from epomaker_driver.mouse_codec import (
    aggregate,
    dpi,
    dpi_command,
    identity,
    parse_rate,
    profile_command,
    rate_command,
)


def test_identity_decodes_id_and_zero_version_without_boot_claim():
    raw = bytearray(64)
    raw[0] = 0x8F
    raw[1:5] = (3961).to_bytes(4, "little")
    result = identity(raw)
    assert result["device_id"] == 3961
    assert result["usb_version"] is None
    assert result["is_boot"] is None
    assert result["raw"] == list(raw)


def test_dpi_decodes_offsets_and_raw():
    raw = bytearray(64)
    raw[:4] = bytes([0x90, 3, 2, 4])
    raw[8:10] = (1000).to_bytes(2, "little")
    raw[24:26] = (1200).to_bytes(2, "little")
    raw[40:43] = bytes.fromhex("123456")
    result = dpi(raw)
    assert result["profile"] == 3
    assert result["current"] == 2
    assert result["count"] == 4
    assert result["levels"][0] == {"x": 1000, "y": 1200, "rgb": 0x123456}
    assert result["raw"] == list(raw)


def test_dpi_command_preserves_levels_clears_reserved_header_and_recomputes_checksum():
    raw = bytearray(range(64))
    raw[0] = 0x90
    original = bytes(raw)
    command = dpi_command(raw, profile=4, current=1, slot=2, x=321, rgb=0xABCDEF)
    assert command[0] == 0x10
    assert command[4:7] == bytes(3)
    assert command[1] == 4
    assert command[2] == 1
    assert command[8:10] == original[8:10]
    assert command[10:12] == original[10:12]
    assert command[14:24] == original[14:24]
    assert command[40:46] == original[40:46]
    assert command[49:] == original[49:]
    assert command[8 + 4 : 10 + 4] == (321).to_bytes(2, "little")
    assert command[46:49] == bytes.fromhex("abcdef")
    assert command[7] == 255 - (sum(command[:7]) & 255)


@pytest.mark.parametrize(
    "hz,code", [(125, 8), (250, 4), (500, 2), (1000, 1), (2000, 132), (4000, 130), (8000, 129)]
)
def test_report_rate_codec(hz, code):
    command = rate_command(hz)
    assert command[:2] == bytes([8, code])
    response = bytearray(64)
    response[:2] = bytes([0x88, code])
    assert parse_rate(response) == hz


def test_unknown_report_rate_is_preserved_as_none():
    response = bytearray(64)
    response[:2] = bytes([0x88, 77])
    assert parse_rate(response) is None


def test_aggregate_decodes_offsets_and_unknown_rates():
    raw = bytearray(64)
    raw[0] = 0x9F
    raw[8:20] = bytes([3, 10, 7, 0x2C, 0x01, 0x90, 0x01, 1, 0, 1, 1, 0])
    raw[20:28] = bytes([8, 4, 2, 1, 132, 130, 129, 77])
    raw[28] = 1
    raw[40] = 9
    result = aggregate(raw)
    assert result["profile"] == 3
    assert result["sleep_24g"] == 300
    assert result["sleep_bluetooth"] == 400
    assert result["report_rates"][-1] is None
    assert result["low_latency"] == 9
    assert result["raw"] == list(raw)


@pytest.mark.parametrize(
    "factory,args", [(identity, (bytes(64),)), (dpi, (bytes(64),)), (aggregate, (bytes(64),))]
)
def test_parsers_reject_wrong_opcode(factory, args):
    with pytest.raises(ValueError):
        factory(*args)


@pytest.mark.parametrize("value", [True, -1, 8, 1.5])
def test_dpi_command_rejects_invalid_integer_arguments(value):
    raw = bytearray(64)
    raw[0] = 0x90
    with pytest.raises(ValueError):
        dpi_command(raw, profile=value, current=0)


def test_dpi_command_requires_meaningful_patch_and_slot():
    raw = bytearray(64)
    raw[0] = 0x90
    with pytest.raises(ValueError):
        dpi_command(raw, profile=0)
    with pytest.raises(ValueError):
        dpi_command(raw, profile=0, slot=0)
    with pytest.raises(ValueError):
        dpi_command(raw, profile=0, x=1)


def test_profile_command_uses_common_packet_checksum():
    command = profile_command(3)
    assert command[:2] == bytes([2, 3])
    assert command == codec.packet([2, 3])


@pytest.mark.parametrize("factory", [identity, dpi, aggregate])
@pytest.mark.parametrize("raw", [b"", bytes(63), bytes(65), None, "not bytes"])
def test_parsers_reject_invalid_raw_length_or_type(factory, raw):
    with pytest.raises(ValueError):
        factory(raw)


@pytest.mark.parametrize("count", [0, 9, True, 1.5])
def test_dpi_command_rejects_invalid_count(count):
    raw = bytearray(64)
    raw[0] = 0x90
    with pytest.raises(ValueError):
        dpi_command(raw, profile=0, count=count)


@pytest.mark.parametrize("hz", [0, 124, 125.0, True, 9000])
def test_rate_command_rejects_unknown_or_noninteger_rate(hz):
    with pytest.raises(ValueError):
        rate_command(hz)


def test_parse_rate_rejects_wrong_opcode():
    with pytest.raises(ValueError):
        parse_rate(bytes(64))
