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
    assert status["capabilities"] == [
        "keymap",
        "fn",
        "macro",
        "profile",
        "debounce",
        "os",
        "sleep",
        "lighting",
    ]
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
        lambda k: k.set_light("solid", side=True),
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


def test_sleep_preserves_hidden_field_and_checks_model_limits(ry, firmware):
    minimum = model_by_id(firmware.model_id)["other"]["sleepBT"]["sleep"]["min"]
    firmware.sleep_data[14:16] = bytes.fromhex("ffff")
    result = ry.set_sleep(minimum, 64800, minimum)
    assert result == {"bluetooth": minimum, "dongle": 64800, "deep_bluetooth": minimum}
    assert firmware.sent[-1][14:16] == bytes.fromhex("ffff")
    assert ry.get_sleep() == result
    assert "deep_dongle" not in ry.status()["sleep"]
    before = len(firmware.sent)
    for values in [
        (minimum - 1, minimum, minimum),
        (minimum, 64801, minimum),
        (minimum, minimum, minimum - 1),
        (minimum, minimum, minimum, 600),
    ]:
        with pytest.raises(ValueError):
            ry.set_sleep(*values)
    assert len(firmware.sent) == before


def test_sleep_failed_read_prevents_write(ry, firmware):
    from epomaker_driver.errors import ProtocolError

    exchange = firmware.exchange
    firmware.exchange = lambda command, **kwargs: (
        bytes(63) if command[0] == 0x91 else exchange(command, **kwargs)
    )
    with pytest.raises(ProtocolError):
        ry.set_sleep(600, 600, 600)
    assert not firmware.sent


def test_sleep_detects_hidden_field_mutation(ry, firmware):
    from epomaker_driver.errors import ProtocolError

    send = firmware.send

    def mutate(command, **kwargs):
        send(command, **kwargs)
        if command[0] == 0x11:
            firmware.sleep_data[14:16] = bytes.fromhex("1234")

    firmware.send = mutate
    with pytest.raises(ProtocolError, match="sleep readback"):
        ry.set_sleep(600, 600, 600)
    assert len(firmware.sent) == 1


@pytest.mark.parametrize("mode", [m for m in codec.LIGHT_MODES if m != "off"])
@pytest.mark.parametrize("rainbow", [False, True])
def test_lighting_model_flags_and_readback(ry, firmware, mode, rainbow):
    normal, dazzle = (8, 7) if firmware.model_id in (3573, 3674) else (7, 8)
    value = ry.set_light(mode, rgb=0x123456, speed=3, brightness=2, rainbow=rainbow)
    flag = dazzle if rainbow else normal
    if mode in ("picture", "screen"):
        flag = 0
    elif mode == "music":
        flag = 0 if rainbow else 4
    command = firmware.sent[-1]
    assert command[0:5] == bytes([7, codec.LIGHT_MODES[mode], 1, 2, flag])
    assert value["mode"] == mode and value["speed"] == 3
    if mode not in ("picture", "screen"):
        assert value["rainbow"] is rainbow


@pytest.mark.parametrize("mode", ["wave", "snake", "breathing", "off"])
def test_side_effects_only_on_declared_models(ry, firmware, mode):
    if firmware.model_id in (3858, 3633):
        with pytest.raises(UnsupportedDevice):
            ry.set_light(mode, side=True)
        with pytest.raises(UnsupportedDevice):
            ry.get_light(side=True)
        assert not firmware.sent
        return
    value = ry.set_light(mode, side=True, rainbow=True, speed=3)
    assert value["mode"] == mode and value["rainbow"]
    assert firmware.sent[-1][4] == (7 if firmware.model_id in (3573, 3674) else 8)
    before = len(firmware.sent)
    with pytest.raises(ValueError):
        ry.set_light(mode, side=True, speed=4)
    assert len(firmware.sent) == before


def test_model_preset_palette(ry, firmware):
    palettes = {
        3573: [16711680, 65280, 255, 16733440, 7799039, 16776960, 16777215],
        3674: [16711680, 65280, 255, 16776960, 16732250, 65535, 16777215],
    }
    expected = palettes.get(
        firmware.model_id, [0xFF0000, 0xFF8000, 0xFFFF00, 0x00FF00, 0x00FFFF, 0x0000FF, 0xFF00FF]
    )
    for index, rgb in enumerate(expected):
        firmware.light[1] = 1
        firmware.light[4] = index
        assert ry.get_light()["rgb"] == rgb


def test_rgb_pictures_and_rejected_main_off(ry, firmware):
    colors = bytes(i % 256 for i in range(378))
    ry.write_picture(colors, 4)
    assert ry.read_picture(4) == colors
    ry.set_picture_key(4, 125, 0xABCDEF)
    assert ry.read_picture(4)[375:] == bytes.fromhex("abcdef")
    ry.set_light("picture", option=4)
    assert firmware.light[4] == 64
    before = len(firmware.sent)
    with pytest.raises(UnsupportedDevice):
        ry.set_light("off")
    assert len(firmware.sent) == before
    assert ry.set_light("solid", brightness=0)["brightness"] == 0
