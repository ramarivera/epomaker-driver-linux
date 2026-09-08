"""All migrated RY6602 models, using a simulated USB feature-report link."""

import pytest

from epomaker_driver import codec
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

    firmware.sleep_data = bytearray(codec.sleep_times(600, 1200, 1800, 3600))
    firmware.side_light = bytearray(codec.light("breathing", side=True))

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
    ] + (["display"] if firmware.model_id in (3858, 3673, 3674) else [])
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
        lambda k: k.sync_clock(),
        lambda k: k._write([codec.packet([4]), codec.packet([0x27])]),
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


def test_rgb24_still_and_animation(ry, firmware):
    from epomaker_driver.models import display_spec

    if firmware.model_id not in (3858, 3673, 3674):
        with pytest.raises(UnsupportedDevice):
            ry.upload_screen(bytes(3), (0, 0, 1, 1))
        assert ry.status()["display"] is None
        return
    width, height, maximum = {3858: (33, 7, 255), 3673: (7, 7, 255), 3674: (7, 7, 16)}[
        firmware.model_id
    ]
    assert display_spec(firmware.model_id) == {
        "width": width,
        "height": height,
        "banks": 5,
        "max_frames": maximum,
        "pixel_bytes": 3,
    }
    prepares = []
    exchange = firmware.exchange

    def track(command, **kwargs):
        if command[0] == 0xA9:
            prepares.append(command)
        return exchange(command, **kwargs)

    firmware.exchange = track
    pixels = bytes.fromhex("123456") * (width * height)
    ry.upload_screen(pixels, (0, 0, width, height), frame=4)
    assert prepares[0][0:4] == bytes([0xA9, 4, 1, 0])
    assert prepares[0][8:12] == bytes([0, 0, width, height])
    assert all(p[0] == 0x29 for p in firmware.sent)
    assert b"".join(p[8 : 8 + p[6]] for p in firmware.sent) == pixels
    firmware.sent.clear()
    ry.upload_animation([pixels] * maximum, 80)
    chunks = (len(pixels) + 55) // 56
    assert len(firmware.sent) == chunks * maximum
    assert prepares[-1][2:4] == bytes([maximum, 80])
    assert firmware.sent[chunks][1:6] == bytes([1, maximum, 80, 0, 0])
    assert firmware.sent[-1][1] == maximum - 1
    before = len(firmware.sent)
    with pytest.raises(ValueError):
        ry.upload_animation([pixels] * (maximum + 1), 80)
    with pytest.raises(ValueError):
        ry.upload_screen(bytes(width * height * 2), (0, 0, width, height))
    assert len(firmware.sent) == before


def test_recovery_snapshot_preserves_current_hidden_timer(ry, firmware, tmp_path):
    import json

    from epomaker_driver import snapshot

    mid = firmware.model_id
    firmware.sleep_data[14:16] = bytes.fromhex("ffff")
    original = snapshot.capture(ry)
    assert original["schema_version"] == 5
    assert "deep_dongle" not in original["sleep"]
    assert (original["side_light"] is None) == (mid in (3858, 3633))
    ry.set_sleep(1200, 1200, 1200)
    ry.set_key(9, [0, 0, 5, 0], profile=len(firmware.matrices) - 1)
    firmware.sleep_data[14:16] = bytes.fromhex("1234")
    path = tmp_path / "before.json"
    result = snapshot.restore(ry, original, path)
    assert result["restored"]
    assert "unexposed receiver timer field is not restored" in result["limitations"]
    assert firmware.sleep_data[14:16] == bytes.fromhex("1234")
    assert snapshot.capture(ry) == original
    assert json.loads(path.read_text())["sleep"]["bluetooth"] == 1200
    assert all(p[0] != 8 for p in firmware.sent) if mid in (3858, 3633) else True


@pytest.mark.parametrize(
    "damage",
    [
        lambda v: v.update(schema_version=4),
        lambda v: v["sleep"].update(deep_dongle=600),
        lambda v: v["sleep"].update(bluetooth=-1),
        lambda v: v["matrices"].pop(),
    ],
)
def test_invalid_family_snapshots_fail_before_writes(ry, firmware, tmp_path, damage):
    from epomaker_driver import snapshot

    value = snapshot.capture(ry)
    damage(value)
    with pytest.raises(ValueError):
        snapshot.restore(ry, value, tmp_path / "recovery.json")
    assert not firmware.sent and not (tmp_path / "recovery.json").exists()


def test_snapshot_side_capability_validation(ry, firmware):
    from epomaker_driver import snapshot

    value = snapshot.capture(ry)
    if value["side_light"] is None:
        value["side_light"] = {"raw": list(codec.packet([0x88]))}
    else:
        value["side_light"]["raw"][1] = 1  # solid is absent from this side layout
    with pytest.raises(ValueError, match="side"):
        snapshot.validate(value)
    assert not firmware.sent


def test_reset_recovery_exists_before_command(ry, firmware, tmp_path):
    import json

    from epomaker_driver import snapshot

    firmware.macros[255] = bytearray([123] * 256)
    destination = tmp_path / "reset.json"
    send = firmware.send

    def checked(command, **kwargs):
        saved = json.loads(destination.read_text())
        assert saved["schema_version"] == 5 and len(saved["macros"]) == 256
        assert saved["macros"]["255"] == bytes([123] * 256).hex()
        assert len(saved["matrices"]) == len(firmware.matrices)
        send(command, **kwargs)

    firmware.send = checked
    result = snapshot.factory_reset(ry, destination)
    assert result["reset_sent"] and not result["factory_defaults_verified"]
    assert firmware.sent == [codec.packet([1])]
    assert ry.identity is None


def test_cross_model_recovery_is_rejected(ry, firmware, tmp_path):
    from epomaker_driver import snapshot

    value = snapshot.capture(ry)
    firmware.model_id = 3059
    with pytest.raises(ValueError, match="does not match"):
        snapshot.restore(ry, value, tmp_path / "bad.json")
    assert not firmware.sent and not (tmp_path / "bad.json").exists()
