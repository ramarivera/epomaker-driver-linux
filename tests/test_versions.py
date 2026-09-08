import pytest

from epomaker_driver.versions import parse_version, version_request


@pytest.mark.parametrize(
    ("component", "header", "reply", "expected"),
    [
        ("usb", "8f00000000000070", "8f7856341200aa0005", 0x0500),
        ("rf", "800000000000007f", "803412", 0x1234),
        ("mled", "ae00000000000051", "ae0104", 0x0401),
        ("oled", "ad00000000000052", "ad0203cdab", {"oled": 0x0302, "flash": 0xABCD}),
    ],
)
def test_version_wire_fixtures(component, header, reply, expected):
    assert version_request(component) == bytes.fromhex(header) + bytes(56)
    response = bytes.fromhex(reply)
    assert parse_version(component, response) == expected
    assert parse_version(component, response.ljust(64, b"\xff")) == expected


@pytest.mark.parametrize("component", ["usb", "rf", "mled", "oled"])
def test_version_zero_is_unavailable_and_malformed_replies_fail(component):
    raw = bytearray(version_request(component))
    raw[7] = 0  # Request checksum is not version data in a reply.
    expected = {"oled": None, "flash": None} if component == "oled" else None
    assert parse_version(component, raw) == expected
    for invalid in (b"", bytes([raw[0]]), bytes(64), raw + b"\x00"):
        with pytest.raises(ValueError, match="version response"):
            parse_version(component, invalid)


def test_oled_components_are_independently_optional():
    assert parse_version("oled", bytes.fromhex("ad00000102")) == {"oled": None, "flash": 0x0201}
    assert parse_version("oled", bytes.fromhex("ad01020000")) == {"oled": 0x0201, "flash": None}


def test_unknown_version_component_rejected():
    with pytest.raises(ValueError, match="component"):
        version_request("receiver")
    with pytest.raises(ValueError, match="component"):
        parse_version("receiver", bytes(64))
