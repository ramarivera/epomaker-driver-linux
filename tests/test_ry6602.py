"""All migrated RY6602 models, using a simulated USB feature-report link."""

import pytest

from epomaker_driver import codec, snapshot
from epomaker_driver.device import Keyboard
from epomaker_driver.discovery import classify, parse_descriptor
from epomaker_driver.errors import UnsupportedDevice
from epomaker_driver.models import RY6602_IDS, default_matrix, model_by_id
from epomaker_driver.transport import Transport


@pytest.fixture(params=RY6602_IDS)
def ry(request, firmware):
    mid = request.param
    firmware.model_id = mid
    firmware.matrices = [bytearray(default_matrix(mid)) for _ in range(model_by_id(mid)["layer"])]
    firmware.fn = [
        bytearray(default_matrix(mid, name)) for name in ("defaultFnMatrix", "defaultFnMacMatrix")
    ]

    class USB:
        response = b""

        def set_feature(self, data):
            assert len(data) == 65 and data[0] == 0
            command = data[1:]
            if command[0] >= 128:
                self.response = firmware.exchange(command)
            else:
                firmware.send(command)

        def get_feature(self, report_id, length):
            assert report_id == 0 and length == 64
            return self.response

        def close(self):
            firmware.close()

    return Keyboard(Transport(USB(), "usb", sleep=lambda _: None))


def test_usb_core_roundtrip(ry, firmware):
    status = ry.status()
    assert status["profiles"] == (4 if firmware.model_id == 3858 else 3)
    assert status["capabilities"] == ["keymap", "fn", "macro", "profile", "debounce", "os"]
    last = status["profiles"] - 1
    before = ry.read_matrix(0)
    ry.set_profile(last)
    ry.set_key(9, [0, 0, 5, 0], profile=last)
    assert ry.read_matrix(last)[36:40] == bytes([0, 0, 5, 0])
    assert ry.read_matrix(0) == before
    ry.write_matrix(bytes(range(256)) * 2, last)
    assert ry.read_matrix(last) == bytes(range(256)) * 2
    ry.write_macro(255, bytes([120]) * 256)
    assert ry.read_macro(255) == bytes([120]) * 256
    ry.set_key(9, [9, 0, 255, 0], profile=last)
    assert ry.read_matrix(last)[36:40] == bytes([9, 0, 255, 0])
    with pytest.raises(ValueError):
        ry.set_profile(last + 1)


@pytest.mark.parametrize("os_mode", [0, 1])
def test_fn_and_os_controls(ry, firmware, os_mode):
    untouched = bytes(firmware.fn[1 - os_mode])
    original = ry.read_matrix(fn=True, os_mode=os_mode)
    ry.set_key(9, [0, 0, 6, 0], fn=True, os_mode=os_mode)
    assert ry.read_matrix(fn=True, os_mode=os_mode)[36:40] == bytes([0, 0, 6, 0])
    ry.write_fn_matrix(original, os_mode)
    assert ry.read_matrix(fn=True, os_mode=os_mode) == original
    assert bytes(firmware.fn[1 - os_mode]) == untouched
    before = bytes(firmware.options)
    ry.set_options(system="mac" if os_mode else "win", wasd_swap=True)
    assert firmware.options[1] == os_mode
    assert firmware.options[2:5] == before[2:5] and firmware.options[6] == before[6]
    ry.set_auto_os(True)
    ry.set_debounce(10)
    assert ry.status()["auto_os"] and ry.status()["debounce"] == 10


@pytest.mark.parametrize(
    "operation",
    [
        lambda k: k.set_light("solid"),
        lambda k: k.set_sleep(600, 600, 600, 600),
        lambda k: k.upload_screen(bytes(2), (0, 0, 1, 1)),
        lambda k: snapshot.capture(k),
        lambda k: k._write([codec.packet([4]), codec.packet([1])]),
    ],
)
def test_unmigrated_operations_cannot_write(ry, firmware, operation):
    with pytest.raises(UnsupportedDevice):
        operation(ry)
    assert not firmware.sent


def test_usb_filter_requires_exact_command_collection():
    descriptor = bytes.fromhex("06ffff 0902 a101 7508 9540 b102 c0")
    assert classify(3, 0x3151, 0x5056, parse_descriptor(descriptor)) == ("usb", 0)
    for bad in [
        descriptor.replace(bytes.fromhex("9540"), bytes.fromhex("953f")),
        descriptor.replace(bytes.fromhex("0902"), bytes.fromhex("0906")),
    ]:
        assert classify(3, 0x3151, 0x5056, parse_descriptor(bad)) == (None, None)
    assert classify(3, 0x3151, 0x5058, parse_descriptor(descriptor)) == (None, None)
    assert classify(5, 0x3151, 0x5056, parse_descriptor(descriptor)) == (None, None)
