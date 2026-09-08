import pytest

from epomaker_driver.magnetic import (
    assemble_pages,
    decode_field,
    decode_page,
    encode_field,
    encode_read,
    encode_write,
    field_write_order,
    key_field,
    top_dead_zone_supported,
    travel_multiplier,
    write_commands,
)


@pytest.mark.parametrize(
    ("version", "expected"), [(None, 10), (0x02FF, 10), (0x0300, 100), (0x04FF, 100), (0x0500, 200)]
)
def test_version_scaling(version, expected):
    assert travel_multiplier(usb=version) == expected


def test_rf_version_takes_precedence_and_top_dead_zone_gate():
    assert travel_multiplier(usb=0x0500, rf=0x0200) == 10
    assert travel_multiplier(usb=0x0500, rf=0) == 200
    assert top_dead_zone_supported(usb=0x0200, rf=0x0400) is True
    assert top_dead_zone_supported(usb=0x03FF) is False
    assert top_dead_zone_supported(usb=0x0400) is True


def test_known_wire_headers_and_unknown_payload_preservation():
    assert encode_read(0, 3).hex() == "e500010300000016" + "00" * 56
    assert encode_write(6, 17, b"\x34\x12", commit=True).hex() == "65060011010000823412" + "00" * 54
    response = bytes.fromhex("e500010300000000") + bytes(56)
    assert decode_page(response)[0:8] == bytes.fromhex("e500010300000000")
    pages = [bytes(range(64)), bytes(range(64))]
    assert assemble_pages(pages, length=100)[-1] == 35
    staged = bytes(128) + bytes([1]) * 128 + bytes([2]) * 128 + bytes([3]) * 128
    assert key_field(staged, 7, field=10, stage=2) == 2
    assert key_field(bytes([0x34]) + bytes(127), 0, field=5) == b"\x34"
    words = bytes.fromhex("01003412") + bytes(252)
    assert key_field(words, 1, field=0) == b"\x34\x12"
    assert key_field(bytes(254) + b"\xab\xcd", 127, field=6) == b"\xab\xcd"
    assert encode_read(252, 1).hex() == "e5fc01010000001c" + "00" * 56


def test_field_roundtrip_and_bounds():
    raw = encode_field(0, 1.239, multiplier=100)
    assert raw == bytes.fromhex("7b00")
    assert decode_field(0, raw, multiplier=100) == 1.23
    assert encode_field(5, 120, multiplier=100) == b"\x0c"
    assert decode_field(5, b"\x0c", multiplier=100) == 120
    assert encode_field(8, b"\x01\x02\x03\x04", multiplier=100) == b"\x01\x02\x03\x04"
    with pytest.raises(ValueError):
        encode_field(5, 11, multiplier=100)
    with pytest.raises(ValueError):
        encode_write(0, 0, bytes(57), commit=False)
    with pytest.raises(ValueError):
        encode_write(0, 128, b"", commit=False)
    with pytest.raises(ValueError):
        encode_write(0, 0, b"", commit=1)
    with pytest.raises(ValueError):
        encode_read(8, 0)
    with pytest.raises(ValueError):
        encode_read(0, 4)
    with pytest.raises(ValueError):
        encode_read(7, 2)
    with pytest.raises(ValueError):
        encode_field(253, 0, multiplier=100)
    assert encode_field(251, 0.75, multiplier=200) == b"\x96"
    assert decode_field(251, b"\x96", multiplier=200) == 0.75
    with pytest.raises(ValueError):
        encode_field(10, 0, multiplier=100)
    with pytest.raises(ValueError):
        decode_field(10, b"\x00", multiplier=100)
    with pytest.raises(ValueError):
        encode_field(8, 4, multiplier=100)


def test_field_order_and_unknown_fields_are_strict():
    assert field_write_order(
        changed={7, 0, 1, 6, 2, 3, 4, 8, 5, 251}, mode_changed=True, top_supported=True
    ) == [
        7,
        0,
        1,
        6,
        2,
        3,
        4,
        8,
        5,
        251,
    ]
    with pytest.raises(ValueError):
        field_write_order(changed={10}, mode_changed=False, top_supported=True)
    with pytest.raises(ValueError):
        field_write_order(changed={251}, mode_changed=False, top_supported=False)
    commands = write_commands({7: 2, 0: 1.2, 5: 20}, key_index=3, multiplier=100, mode_changed=True)
    assert [command[4] for command in commands] == [0, 0, 1]
    assert commands[0][1] == 7 and commands[-1][1] == 5
    assert commands == [
        bytes.fromhex("650700030000009002") + bytes(55),
        bytes.fromhex("65000003000000977800") + bytes(54),
        bytes.fromhex("650500030100009102") + bytes(55),
    ]
    assert write_commands({7: 0x80}, key_index=0, multiplier=10, mode_changed=True) == [
        bytes.fromhex("650700000100009280") + bytes(55)
    ]
    assert write_commands({}, key_index=0, multiplier=10) == []
    with pytest.raises(ValueError):
        field_write_order(changed={252}, mode_changed=False, top_supported=True)
    with pytest.raises(ValueError):
        field_write_order(changed={7}, mode_changed=False, top_supported=True)
    with pytest.raises(ValueError):
        field_write_order(changed={0}, mode_changed=True, top_supported=True)
    commands = write_commands({0: 1.0, 1: 2.0}, key_index=1, multiplier=100)
    assert commands[0][4] == 0 and commands[-1][4] == 1
    with pytest.raises(ValueError):
        encode_write(10, 0, b"\x00", commit=True)
    with pytest.raises(ValueError):
        encode_write(0, 0, 1, commit=True)
    with pytest.raises(ValueError):
        key_field(bytes(1), 1, field=5)
    with pytest.raises(ValueError):
        key_field(bytes(512), 0, field=10, stage=4)
    with pytest.raises(ValueError):
        top_dead_zone_supported(usb=True)
    assert top_dead_zone_supported(rf=0) is False
    with pytest.raises(ValueError):
        write_commands({}, key_index=0, multiplier=7)
    with pytest.raises(ValueError):
        write_commands({}, key_index=0, multiplier=100, mode_changed=1)


@pytest.mark.parametrize("bad", [True, -1, 0x10000, "1"])
def test_invalid_versions_and_pages(bad):
    with pytest.raises(ValueError):
        travel_multiplier(usb=bad)
    with pytest.raises(ValueError):
        top_dead_zone_supported(rf=bad)
    with pytest.raises(ValueError):
        encode_read(0, bad)


def test_remaining_width_and_range_guards():
    with pytest.raises(ValueError):
        decode_page(bytes(63))
    with pytest.raises(ValueError):
        assemble_pages([bytes(64)], length=65)
    with pytest.raises(ValueError):
        key_field(bytes(1), 0, field=0)
    with pytest.raises(ValueError):
        key_field(bytes(64), 0, field=10, stage=0)
    with pytest.raises(ValueError):
        encode_field(251, 2, multiplier=200)
    with pytest.raises(ValueError):
        encode_field(251, float("nan"), multiplier=200)
    with pytest.raises(ValueError):
        encode_field(7, 256, multiplier=100)
    with pytest.raises(ValueError):
        encode_field(8, b"\x00", multiplier=100)
    with pytest.raises(ValueError):
        encode_field(0, float("nan"), multiplier=100)
    with pytest.raises(ValueError):
        encode_field(0, 1000, multiplier=100)
    with pytest.raises(ValueError):
        decode_field(251, b"\x00\x01", multiplier=100)
    with pytest.raises(ValueError):
        decode_field(7, b"\x00\x01", multiplier=100)
    with pytest.raises(ValueError):
        decode_field(8, b"\x00", multiplier=100)
    with pytest.raises(ValueError):
        decode_field(5, b"\x00\x01", multiplier=100)
    with pytest.raises(ValueError):
        decode_field(0, b"\x00\x01\x02", multiplier=100)
    with pytest.raises(ValueError):
        decode_field(0, b"\x00", multiplier=7)
    with pytest.raises(ValueError):
        encode_read(300, 0)
    with pytest.raises(ValueError):
        key_field(bytes(128), 0, field=8)
    assert decode_field(252, b"\x05", multiplier=100) == 5
    assert decode_field(8, b"\x01\x02\x03\x04", multiplier=100) == b"\x01\x02\x03\x04"


@pytest.mark.parametrize("field", [0, 1, 2, 3, 4, 6, 251])
@pytest.mark.parametrize("multiplier", [100, 200])
def test_decimal_travel_does_not_lose_one_wire_unit(field, multiplier):
    # 0.29 * 100 is below 29 in binary floating-point; the UI quantum is exact.
    raw = encode_field(field, 0.29, multiplier=multiplier)
    assert int.from_bytes(raw, "little") == (29 if multiplier == 100 else 58)
    assert decode_field(field, raw, multiplier=multiplier) == 0.29
