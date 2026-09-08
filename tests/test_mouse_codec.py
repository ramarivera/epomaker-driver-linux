import pytest

from epomaker_driver import codec
from epomaker_driver.mouse_codec import (
    SETTINGS,
    aggregate,
    dpi,
    dpi_command,
    identity,
    parse_rate,
    parse_setting,
    profile_command,
    rate_command,
    setting_command,
    setting_query,
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


@pytest.mark.parametrize(
    ("name", "get_opcode", "set_opcode", "value"),
    [
        ("debounce", 0x84, 0x04, 10),
        ("scroll_up_time", 0x85, 0x05, 255),
        ("sleep_24", 0x86, 0x06, 0x1234),
        ("sleep_bt", 0x87, 0x07, 0xFEDC),
        ("lod", 0x91, 0x11, 2),
        ("line_repair", 0x92, 0x12, True),
        ("wave_repair", 0x93, 0x13, False),
        ("low_latency", 0x8C, 0x0C, 1),
    ],
)
def test_scalar_settings_have_exact_query_write_and_parse_wire_values(
    name, get_opcode, set_opcode, value
):
    query = setting_query(name)
    command = setting_command(name, value)
    assert query == codec.packet([get_opcode])
    expected = [set_opcode]
    if name in {"sleep_24", "sleep_bt"}:
        expected.extend((value & 255, value >> 8))
    else:
        expected.append(int(value))
    assert command == codec.packet(expected)
    response = bytearray(64)
    response[0] = get_opcode
    if name in {"sleep_24", "sleep_bt"}:
        response[1:3] = int(value).to_bytes(2, "little")
    else:
        response[1] = int(value)
    assert parse_setting(name, response) == value
    assert command[7] == (255 - sum(command[:7])) & 255


@pytest.mark.parametrize("name", list(SETTINGS))
@pytest.mark.parametrize("raw", [b"", bytes(63), bytes(65), None, "not bytes"])
def test_scalar_parsers_reject_wrong_length_or_type(name, raw):
    with pytest.raises(ValueError):
        parse_setting(name, raw)


@pytest.mark.parametrize("name", ["debounce", "scroll_up_time", "sleep_24", "sleep_bt", "lod"])
def test_scalar_parsers_reject_wrong_opcode(name):
    raw = bytearray(64)
    raw[0] = 0xFF
    with pytest.raises(ValueError):
        parse_setting(name, raw)


@pytest.mark.parametrize(
    ("name", "values"),
    [
        ("debounce", [True, False, 0, 11, 1.0, -1]),
        ("scroll_up_time", [True, False, 0, 256, 1.0, -1]),
        ("sleep_24", [True, -1, 65536, 1.0]),
        ("sleep_bt", [True, -1, 65536, 1.0]),
        ("lod", [True, -1, 3, 1.0]),
        ("low_latency", [True, -1, 2, 1.0]),
    ],
)
def test_scalar_commands_reject_invalid_numeric_values(name, values):
    for value in values:
        with pytest.raises(ValueError):
            setting_command(name, value)


@pytest.mark.parametrize("name", ["line_repair", "wave_repair"])
@pytest.mark.parametrize("value", [0, 1, 2, None, 1.0, "true"])
def test_boolean_scalar_commands_require_actual_bool(name, value):
    with pytest.raises(ValueError):
        setting_command(name, value)


def test_scalar_setting_names_are_strict():
    with pytest.raises(ValueError):
        setting_query("sleep")
    with pytest.raises(ValueError):
        setting_command("sleep", 1)
    with pytest.raises(ValueError):
        parse_setting("sleep", bytes(64))


@pytest.mark.parametrize("name", ["line_repair", "wave_repair"])
def test_boolean_scalar_parser_rejects_unknown_flag(name):
    raw = bytearray(64)
    raw[0] = SETTINGS[name][0]
    raw[1] = 2
    with pytest.raises(ValueError):
        parse_setting(name, raw)
