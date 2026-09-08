"""RT85 model boundary and four-profile integration, without physical hardware."""

import pytest

from epomaker_driver import codec
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
    assert model_by_id(2895)["implementation"] == "rt85-partial"
    before = [bytes(m) for m in firmware.matrices]
    rt85.set_profile(3)
    status = rt85.status()
    assert status["profile"] == 3 and status["profiles"] == 4
    assert status["capabilities"] == [
        "keymap",
        "fn",
        "macro",
        "profile",
        "sleep",
        "display",
        "lighting",
        "os",
    ]
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
        lambda k: k.set_debounce(5),
        lambda k: k._write([codec.packet([4, 0]), codec.packet([0x22])]),
    ],
)
def test_unmigrated_operations_never_write(rt85, firmware, operation):
    with pytest.raises(UnsupportedDevice, match="RT85 currently supports"):
        operation(rt85)
    assert firmware.sent == []


def test_default_matrix_errors():
    with pytest.raises(UnsupportedDevice):
        default_matrix(9999)
    with pytest.raises(ValueError):
        default_matrix(2895, "absent")


def test_sleep_limits_and_readback(rt85, firmware):
    from epomaker_driver.errors import ProtocolError

    result = rt85.set_sleep(0, 64800, 10, 64800)
    assert result == {"bluetooth": 0, "dongle": 64800, "deep_bluetooth": 10, "deep_dongle": 64800}
    assert firmware.sent[-1][8:16] == bytes.fromhex("000020fd0a0020fd")
    for values in [(0, 64801, 10, 10), (0, 0, 9, 10), (False, 0, 10, 10)]:
        before = len(firmware.sent)
        with pytest.raises(ValueError):
            rt85.set_sleep(*values)
        assert len(firmware.sent) == before
    firmware.send = lambda *a, **kw: None
    with pytest.raises(ProtocolError, match="sleep readback"):
        rt85.set_sleep(120, 120, 600, 600)


def test_display_banks_dimensions_and_commands(rt85, firmware):
    import datetime

    from epomaker_driver.models import display_spec

    assert display_spec(2895) == {"width": 320, "height": 172, "banks": 5, "max_frames": 51}
    before = firmware.exchange
    prepares = []

    def track(command, **kwargs):
        if command[0] == 0xA5:
            prepares.append(command)
        return before(command, **kwargs)

    firmware.exchange = track
    pixels = bytes.fromhex("f800") * (320 * 172)
    rt85.upload_screen(pixels, (0, 0, 320, 172), frame=4)
    assert prepares[0][1:4] == bytes([4, 1, 0])
    assert prepares[0][8:16] == bytes([0, 0, 64, 172, 0, 0, 1, 0])
    assert b"".join(p[8 : 8 + p[6]] for p in firmware.sent) == pixels
    assert len(firmware.sent) == 1966
    rt85.toggle_display_language()
    assert firmware.sent[-1] == codec.packet([0x27, 1])
    rt85.sync_clock(datetime.datetime(2026, 9, 8, 12, 34, 56))
    assert firmware.sent[-1] == codec.clock_command(2026, 9, 8, 12, 34, 56)
    before_count = len(firmware.sent)
    with pytest.raises(ValueError, match="320x172"):
        rt85.upload_screen(bytes(428 * 142 * 2), (0, 0, 428, 142))
    with pytest.raises(ValueError, match="memory"):
        rt85.upload_screen(bytes(2), (0, 0, 1, 1), frames=52)
    with pytest.raises(UnsupportedDevice):
        rt85._write([codec.packet([0x22])])
    assert len(firmware.sent) == before_count
    with pytest.raises(UnsupportedDevice):
        display_spec(3223)


def test_animation_model_capacity(rt85, firmware, monkeypatch):
    captured = []
    monkeypatch.setattr(rt85, "_transfer_screen", lambda p, c, progress: captured.append((p, c)))
    frame = bytes.fromhex("07e0") * (320 * 172)
    rt85.upload_animation([frame] * 51, 80)
    prepare, chunks = captured[0]
    assert prepare[2:4] == bytes([51, 80])
    assert len(chunks) == 51 * 1966
    assert chunks[1966][1:6] == bytes([1, 51, 80, 0, 0])
    assert chunks[-1][1] == 50
    for frames in [[frame] * 52, [bytes(428 * 142 * 2)] * 2]:
        with pytest.raises(ValueError):
            rt85.upload_animation(frames, 80)
    assert len(captured) == 1
    assert firmware.sent == []


@pytest.mark.parametrize("mode", list(codec.LIGHT_MODES))
def test_main_lighting_and_readback(rt85, firmware, mode):
    from epomaker_driver.errors import ProtocolError

    value = rt85.set_light(mode, rgb=0x102030, brightness=3, speed=2)
    assert value["mode"] == mode
    assert value["brightness"] == 3 and value["speed"] == 2
    assert firmware.sent[-1][0] == 7
    firmware.send = lambda *a, **kw: None
    with pytest.raises(ProtocolError, match="lighting readback"):
        rt85.set_light(mode, brightness=1)


@pytest.mark.parametrize(
    "mode,speed", [("off", 0), ("solid", 0), ("breathing", 3), ("neon", 3), ("wave", 4)]
)
def test_rt85_side_modes_and_wave_speed(rt85, firmware, mode, speed):
    value = rt85.set_light(mode, side=True, speed=speed, rgb=0x123456)
    assert value["mode"] == mode and value["speed"] == speed
    assert firmware.sent[-1][0] == 8 and firmware.sent[-1][2] == speed
    if mode == "wave":
        assert firmware.sent[-1] == codec.packet([8, 4, 4, 4, 7, 0x12, 0x34, 0x56], 8)


def test_side_model_limits_prevent_writes(rt85, firmware):
    for mode, speed in [("snake", 0), ("breathing", 4), ("neon", 4), ("wave", 5)]:
        with pytest.raises(ValueError):
            rt85.set_light(mode, side=True, speed=speed)
    assert firmware.sent == []
    firmware.model_id = 3059
    glyph = Keyboard(firmware)
    with pytest.raises(ValueError):
        glyph.set_light("wave", side=True, speed=4)
    assert firmware.sent == []
    assert glyph.set_light("snake", side=True, speed=3)["mode"] == "snake"


def test_rt85_options_preserve_unknown_bytes(rt85, firmware):
    from epomaker_driver.errors import ProtocolError

    before = bytes(firmware.options)
    result = rt85.set_options(system="mac", wasd_swap=True)
    assert result["system"] == "mac" and result["wasd_swap"]
    assert bytes(firmware.options[2:5]) == before[2:5]
    assert firmware.options[6] == before[6]
    rt85.set_options(system="win", wasd_swap=False)
    assert rt85.get_options()["system"] == "win"
    for enabled in [True, False]:
        rt85.set_auto_os(enabled)
        assert rt85.get_auto_os() is enabled
    firmware.send = lambda *a, **kw: None
    with pytest.raises(ProtocolError, match="options readback"):
        rt85.set_options(system="mac")
    with pytest.raises(ProtocolError, match="automatic OS"):
        rt85.set_auto_os(True)


def test_rt85_custom_rgb_banks(rt85, firmware):
    colors = bytes(i % 256 for i in range(378))
    for bank in range(5):
        rt85.write_picture(colors, bank)
        assert rt85.read_picture(bank) == colors
        rt85.set_picture_key(bank, 125, 0xABCDEF)
        assert rt85.read_picture(bank)[375:] == bytes.fromhex("abcdef")
        rt85.set_light("picture", option=bank)
        assert firmware.light[1] == 13 and firmware.light[4] == bank << 4
    assert firmware.pictures[0][:375] == colors[:375]
    before = len(firmware.sent)
    with pytest.raises(ValueError):
        rt85.set_light("picture", option=5)
    assert len(firmware.sent) == before
