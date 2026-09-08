import pytest

from epomaker_driver.discovery import Collection, Report, classify, discover, parse_descriptor
from epomaker_driver.errors import ProtocolError


def test_actual_bluetooth_descriptor(descriptor):
    reports = parse_descriptor(descriptor)
    assert reports[6].payload_bytes("input") == 65
    assert reports[6].payload_bytes("output") == 65
    assert reports[6].payload_bytes("feature") == 0
    assert Collection(0xFF55, 0x0202) in reports[6].collections
    assert classify(5, 0x3151, 0x5004, reports) == ("bluetooth", 6)
    assert classify(5, 0x3151, 0x5004, {}) == (None, None)
    assert classify(5, 0x3151, 0x5002, reports) == (None, None)
    assert classify(5, 123, 0x5004, reports) == (None, None)


def test_usb_and_global_stack():
    descriptor = bytes.fromhex("06ffff 0902 a101 7508 9540 a4 7501 b4 b102 c0")
    reports = parse_descriptor(descriptor)
    assert classify(3, 0x3151, 0x5002, reports) == ("usb", 0)
    assert classify(3, 0x3151, 0x5002, {}) == (None, None)
    assert reports[0].feature_bits == 512
    assert parse_descriptor(bytes.fromhex("fe02aa1234")) == {}
    assert parse_descriptor(bytes.fromhex("0b0200ffff a101 7508 9501 8102 c0"))[0].input_bits == 8


@pytest.mark.parametrize(
    "raw",
    [
        "fe",
        "fe03aa01",
        "76ff",
        "8500",
        "85ffb4",
        "c0",
        "a101",
        "a4",
        "7700000100960200b102",
        "750895ffb102b102b102b102b102b102b102b102b102b102b102b102b102b102b102b102b102b102b102b102b102b102b102b102b102b102b102b102b102b102b102b102b102b102",
    ],
)
def test_malformed_descriptor(raw):
    with pytest.raises(ProtocolError):
        parse_descriptor(bytes.fromhex(raw))


def test_discover_metadata(tmp_path, descriptor):
    device = tmp_path / "hidraw9/device"
    device.mkdir(parents=True)
    (device / "uevent").write_text(
        "HID_ID=0005:00003151:00005004\nHID_NAME=Glyph\nHID_UNIQ=private\n"
    )
    (device / "report_descriptor").write_bytes(descriptor)
    result = discover(tmp_path)
    public = result[0].public_dict()
    assert public["path"] == "/dev/hidraw9"
    assert public["command_transport"] == "bluetooth"
    assert "private" not in str(public)
    (tmp_path / "hidraw8/device").mkdir(parents=True)
    assert len(discover(tmp_path)) == 1
    (device / "uevent").write_text("HID_ID=garbage")
    with pytest.raises(ProtocolError, match="invalid HID metadata"):
        discover(tmp_path)


def test_report_invalid_kind():
    with pytest.raises(ValueError):
        Report(0).payload_bytes("bad")
