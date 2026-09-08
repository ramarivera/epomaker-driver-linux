"""RT75 shared protocol coverage, model limits and the vendor Mac-default mismatch."""

import pytest

from epomaker_driver import codec, snapshot
from epomaker_driver.device import Keyboard
from epomaker_driver.errors import UnsupportedDevice
from epomaker_driver.models import default_matrix


@pytest.fixture
def rt75(firmware):
    firmware.model_id = 3223
    firmware.matrices = [bytearray(default_matrix(3223)) for _ in range(3)]
    firmware.fn = [
        bytearray(default_matrix(3223, name)) for name in ("defaultFnMatrix", "defaultFnMacMatrix")
    ]
    return Keyboard(firmware)


def test_keymaps_profiles_and_macros(rt75, firmware):
    before = rt75.read_matrix(0)
    rt75.set_profile(2)
    rt75.set_key(9, [0, 0, 5, 0], profile=2)
    assert rt75.read_matrix(2)[36:40] == bytes([0, 0, 5, 0])
    assert rt75.read_matrix(0) == before
    matrix = bytes(range(256)) * 2
    rt75.write_matrix(matrix, 1)
    assert rt75.read_matrix(1) == matrix
    rt75.write_macro(255, bytes([125]) * 256)
    rt75.set_key(9, [9, 0, 255, 0], profile=2)
    assert rt75.read_macro(255) == bytes([125]) * 256
    assert rt75.read_matrix(2)[36:40] == bytes([9, 0, 255, 0])
    before_count = len(firmware.sent)
    with pytest.raises(ValueError):
        rt75.set_profile(3)
    assert len(firmware.sent) == before_count


@pytest.mark.parametrize("mode", [0, 1])
def test_fn_read_write_uses_actual_matrix(rt75, firmware, mode):
    untouched = bytes(firmware.fn[1 - mode])
    original = rt75.read_matrix(fn=True, os_mode=mode)
    assert len(original) == 512
    rt75.set_key(9, [0, 0, 6, 0], fn=True, os_mode=mode)
    assert rt75.read_matrix(fn=True, os_mode=mode)[36:40] == bytes([0, 0, 6, 0])
    rt75.write_fn_matrix(original, mode)
    assert rt75.read_matrix(fn=True, os_mode=mode) == original
    assert bytes(firmware.fn[1 - mode]) == untouched
    assert default_matrix(3223, "defaultFnMACMatrix") != default_matrix(3223, "defaultFnMacMatrix")


def test_settings_model_limits(rt75, firmware):
    rt75.set_sleep(60, 3600, 60, 3600)
    assert rt75.get_sleep() == {
        "bluetooth": 60,
        "dongle": 3600,
        "deep_bluetooth": 60,
        "deep_dongle": 3600,
    }
    for index in range(4):
        for bad in (0, 59, 3601, True):
            times = [60] * 4
            times[index] = bad
            count = len(firmware.sent)
            with pytest.raises(ValueError):
                rt75.set_sleep(*times)
            assert len(firmware.sent) == count
    rt75.set_debounce(10)
    rt75.set_options(system="mac", wasd_swap=True)
    rt75.set_auto_os(True)
    status = rt75.status()
    assert status["model"] == "RT75" and status["profiles"] == 3
    assert status["debounce"] == 10 and status["auto_os"]
    assert status["options"]["system"] == "mac"
    assert status["capabilities"] == [
        "keymap",
        "fn",
        "macro",
        "profile",
        "sleep",
        "debounce",
        "os",
        "lighting",
        "display",
    ]


@pytest.mark.parametrize(
    "operation",
    [
        lambda k: k.set_light("solid", side=True),
        lambda k: k.set_light("off"),
        lambda k: k.get_light(side=True),
        lambda k: k._write([codec.packet([4]), codec.packet([1])]),
        lambda k: snapshot.capture(k),
    ],
)
def test_unmigrated_features_do_not_write(rt75, firmware, operation):
    with pytest.raises(UnsupportedDevice):
        operation(rt75)
    assert firmware.sent == []


@pytest.mark.parametrize("mode", [m for m in codec.LIGHT_MODES if m != "off"])
def test_main_lighting(rt75, firmware, mode):
    result = rt75.set_light(mode, rgb=0xAA3300, speed=3, brightness=2)
    assert result["mode"] == mode and result["brightness"] == 2
    assert firmware.sent[-1][0] == 7 and firmware.sent[-1][2] == 1


def test_rgb_banks(rt75, firmware):
    colors = bytes(i % 256 for i in range(378))
    rt75.write_picture(colors, 4)
    assert rt75.read_picture(4) == colors
    rt75.set_picture_key(4, 125, 0xABCDEF)
    assert rt75.read_picture(4)[375:] == bytes.fromhex("abcdef")
    rt75.set_light("picture", option=4)
    assert firmware.light[4] == 64


def test_display_dimensions_banks_and_system_info(rt75, firmware):
    from epomaker_driver.models import display_spec

    assert display_spec(3223) == {"width": 240, "height": 240, "banks": 5, "max_frames": 47}
    prepares = []
    exchange = firmware.exchange

    def track(command, **kwargs):
        if command[0] == 0xA5:
            prepares.append(command)
        return exchange(command, **kwargs)

    firmware.exchange = track
    pixels = bytes.fromhex("001f") * 57600
    rt75.upload_screen(pixels, (0, 0, 240, 240), frame=4)
    assert prepares[0][1:4] == bytes([4, 1, 0])
    assert prepares[0][8:16] == bytes([0, 0, 240, 240, 0, 0, 0, 0])
    assert len(firmware.sent) == 2058
    assert b"".join(p[8 : 8 + p[6]] for p in firmware.sent) == pixels
    rt75.sync_clock()
    assert firmware.sent[-1][0] == 0x28
    rt75.toggle_display_language()
    assert firmware.sent[-1] == codec.packet([0x27, 1])
    rt75.sync_system_info(
        {
            "disk_available": 0,
            "disk_total": 1024**3,
            "memory_used": 0,
            "memory_total": 1024**3,
            "network_up": 0,
            "network_down": 0,
            "cpu_usage": 25,
            "cpu_temperature": 40,
        }
    )
    assert firmware.sent[-1][0] == 0x22
    with pytest.raises(ValueError):
        rt75.upload_screen(pixels, (0, 0, 320, 172))


def test_animation_capacity(rt75, monkeypatch):
    transfers = []
    monkeypatch.setattr(rt75, "_transfer_screen", lambda p, c, progress: transfers.append((p, c)))
    frame = bytes(115200)
    rt75.upload_animation([frame] * 47, 100)
    prepare, chunks = transfers[0]
    assert prepare[2:4] == bytes([47, 100])
    assert len(chunks) == 47 * 2058 and chunks[-1][1] == 46
    with pytest.raises(ValueError, match="2..47"):
        rt75.upload_animation([frame] * 48, 100)
    with pytest.raises(ValueError, match="240x240"):
        rt75.upload_animation([bytes(110080)] * 2, 100)
