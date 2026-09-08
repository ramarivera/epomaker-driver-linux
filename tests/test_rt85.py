"""RT85 model boundary and four-profile integration, without physical hardware."""

import pytest

from epomaker_driver import codec, snapshot
from epomaker_driver.device import Keyboard
from epomaker_driver.errors import UnsupportedDevice
from epomaker_driver.models import default_matrix, model_by_id


@pytest.fixture
def rt85(firmware):
    firmware.model_id = 2895
    firmware.matrices = [bytearray(default_matrix(2895)) for _ in range(4)]
    firmware.fn = [
        bytearray(default_matrix(2895, name)) for name in ("defaultFnMatrix", "defaultFnMacMatrix")
    ]
    return Keyboard(firmware)


def test_four_profiles_and_defaults(rt85, firmware):
    assert model_by_id(2895)["implementation"] == "rt85-keymap"
    before = [bytes(m) for m in firmware.matrices]
    rt85.set_profile(3)
    status = rt85.status()
    assert status["profile"] == 3 and status["profiles"] == 4
    assert status["capabilities"] == ["keymap", "fn", "macro", "profile"]
    rt85.set_key(9, [0, 0, 5, 0], profile=3)
    assert rt85.read_matrix(3)[36:40] == bytes([0, 0, 5, 0])
    assert [bytes(m) for m in firmware.matrices[:3]] == before[:3]
    assert firmware.sent[1] == codec.packet([10, 3, 9, 0, 0, 1, 0, 0, 0, 0, 5, 0])
    changed = bytes(range(256)) * 2
    rt85.write_matrix(changed, 3)
    assert rt85.read_matrix(3) == changed
    rt85.write_matrix(before[3], 3)
    assert rt85.read_matrix(3) == before[3]


@pytest.mark.parametrize("mode", [0, 1])
def test_fn_and_macro_roundtrip(rt85, firmware, mode):
    untouched = bytes(firmware.fn[1 - mode])
    matrix = bytearray(rt85.read_matrix(fn=True, os_mode=mode))
    matrix[36:40] = bytes([9, 1, 255, 0])
    rt85.write_fn_matrix(matrix, mode)
    assert rt85.read_matrix(fn=True, os_mode=mode) == matrix
    assert bytes(firmware.fn[1 - mode]) == untouched
    data = codec.macro_data(2, [{"hid_usage": 4, "down": True, "delay_ms": 100}])
    rt85.write_macro(255, data)
    assert rt85.read_macro(255) == data
    rt85.set_key(9, [9, 1, 255, 0], profile=3)
    assert rt85.read_matrix(3)[36:40] == bytes([9, 1, 255, 0])


@pytest.mark.parametrize("method", ["read", "key", "matrix", "profile"])
@pytest.mark.parametrize("model_id,invalid", [(2895, 4), (3059, 3)])
def test_profile_limits_before_writes(firmware, model_id, invalid, method):
    firmware.model_id = model_id
    keyboard = Keyboard(firmware)
    with pytest.raises(ValueError):
        if method == "read":
            keyboard.read_matrix(invalid)
        elif method == "key":
            keyboard.set_key(0, [0, 0, 4, 0], profile=invalid)
        elif method == "matrix":
            keyboard.write_matrix(bytes(512), invalid)
        else:
            keyboard.set_profile(invalid)
    assert firmware.sent == []


@pytest.mark.parametrize(
    "operation",
    [
        lambda k: k.get_light(),
        lambda k: k.set_light("solid"),
        lambda k: k.get_sleep(),
        lambda k: k.set_sleep(60, 60, 600, 600),
        lambda k: k.set_debounce(5),
        lambda k: k.set_options(system="mac"),
        lambda k: k.set_auto_os(True),
        lambda k: k.read_picture(),
        lambda k: k.write_picture(bytes(378)),
        lambda k: k.upload_screen(bytes(2), (0, 0, 1, 1)),
        lambda k: k.sync_clock(),
        lambda k: k._write([codec.packet([4, 0]), codec.packet([1])]),
    ],
)
def test_unmigrated_operations_never_write(rt85, firmware, operation):
    with pytest.raises(UnsupportedDevice, match="RT85 currently supports"):
        operation(rt85)
    assert firmware.sent == []


def test_snapshots_and_reset_refused(rt85, firmware, tmp_path):
    with pytest.raises(UnsupportedDevice, match="snapshots"):
        snapshot.capture(rt85)
    path = tmp_path / "reset.json"
    with pytest.raises(UnsupportedDevice, match="RT85"):
        snapshot.factory_reset(rt85, path)
    assert not path.exists()
    assert firmware.sent == []


def test_default_matrix_errors():
    with pytest.raises(UnsupportedDevice):
        default_matrix(9999)
    with pytest.raises(ValueError):
        default_matrix(2895, "absent")
