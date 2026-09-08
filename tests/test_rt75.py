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
    assert status["capabilities"] == ["keymap", "fn", "macro", "profile", "sleep", "debounce", "os"]


@pytest.mark.parametrize(
    "operation",
    [
        lambda k: k.set_light("solid"),
        lambda k: k.write_picture(bytes(378)),
        lambda k: k.sync_clock(),
        lambda k: k._write([codec.packet([4]), codec.packet([1])]),
        lambda k: k.upload_screen(bytes(2), (0, 0, 1, 1)),
        lambda k: snapshot.capture(k),
    ],
)
def test_unmigrated_features_do_not_write(rt75, firmware, operation):
    with pytest.raises(UnsupportedDevice):
        operation(rt75)
    assert firmware.sent == []
