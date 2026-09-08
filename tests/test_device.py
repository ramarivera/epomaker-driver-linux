import pytest

from epomaker_driver import codec
from epomaker_driver.device import Keyboard
from epomaker_driver.errors import ProtocolError, UnsupportedDevice


def test_settings_roundtrip(firmware):
    k = Keyboard(firmware)
    assert k.identify()["model"] == "Epomaker Glyph"
    assert k.status()["report_rate"] == 1000
    assert k.set_light("wave", rgb=0xAAFF00)["rgb"] == 0xAAFF00
    assert k.set_light("solid", side=True)["rgb"] == 0xFFFFFF
    assert k.set_sleep(60, 120, 600, 1200)["deep_dongle"] == 1200
    k.set_profile(2)
    k.set_debounce(10)
    assert k.status()["profile"] == 2
    assert k.status()["debounce"] == 10
    k.sync_clock()
    assert firmware.sent[-1][0] == 0x28
    with pytest.raises(ValueError):
        k.set_sleep(1, 2, 3, 4)


def test_key_and_matrix_roundtrips(firmware):
    k = Keyboard(firmware)
    initial = k.read_matrix(0)
    assert len(initial) == 512
    assert k.set_key(9, [0, 0, 5, 0]) == [0, 0, 5, 0]
    assert k.read_matrix(0)[36:40] == bytes([0, 0, 5, 0])
    k.write_matrix(initial)
    assert k.read_matrix(0) == initial
    assert k.set_key(9, [0, 0, 6, 0], fn=True, os_mode=1) == [0, 0, 6, 0]


def test_macro_and_picture(firmware):
    k = Keyboard(firmware)
    data = codec.macro_data(
        2,
        [
            {"hid_usage": 4, "down": True, "delay_ms": 128},
            {"hid_usage": 4, "down": False, "delay_ms": 10},
        ],
    )
    k.write_macro(1, data)
    assert k.read_macro(1) == data
    k.write_picture(bytes(378))
    assert len([p for p in firmware.sent if p[0] == 12]) == 7


def test_screen_accept_reject(firmware):
    k = Keyboard(firmware)
    progress = []
    k.upload_screen(bytes(8), (0, 0, 2, 2), progress=progress.append)
    assert progress == [1.0]
    assert firmware.sent[-1][0] == 0x25
    firmware.accept_screen = False
    with pytest.raises(ProtocolError, match="not accepted"):
        k.upload_screen(bytes(8), (0, 0, 2, 2))
    with pytest.raises(ValueError, match="does not match"):
        k.upload_screen(bytes(6), (0, 0, 2, 2))


def test_model_and_boot_gate(firmware):
    firmware.model_id = 1379
    k = Keyboard(firmware)
    with pytest.raises(UnsupportedDevice):
        k.set_light("solid")
    assert not firmware.sent
    firmware.model_id = 3059
    k.identify()
    k.identity["is_boot"] = True
    with pytest.raises(UnsupportedDevice):
        k.set_light("solid")
    assert not firmware.sent


def test_partial_matrix_aborts(firmware, monkeypatch):
    k = Keyboard(firmware)
    k.identify()
    monkeypatch.setattr(firmware, "exchange", lambda *a, **kw: bytes(10))
    with pytest.raises(ProtocolError, match="incomplete matrix"):
        k.read_matrix()
    with pytest.raises(ProtocolError, match="incomplete macro"):
        k.read_macro(1)


@pytest.mark.parametrize("operation", ["key", "matrix", "profile", "debounce", "macro"])
def test_readback_mismatch(operation, firmware, monkeypatch):
    k = Keyboard(firmware)
    k.identify()
    monkeypatch.setattr(firmware, "send", lambda *a, **kw: None)
    with pytest.raises(ProtocolError, match="differs"):
        if operation == "key":
            k.set_key(9, [0, 0, 5, 0])
        elif operation == "matrix":
            k.write_matrix(bytes(512))
        elif operation == "profile":
            k.set_profile(1)
        elif operation == "debounce":
            k.set_debounce(99)
        else:
            k.write_macro(0, bytes([1]) * 256)


def test_options_preserve_fields_and_verify(firmware):
    keyboard = Keyboard(firmware)
    before = bytes(firmware.options)
    result = keyboard.set_options(system="mac", wasd_swap=True)
    assert result["system"] == "mac" and result["wasd_swap"]
    assert bytes(firmware.options[2:5]) == before[2:5]
    assert firmware.options[6] == before[6]
    keyboard.set_options(system="win", wasd_swap=False)
    assert keyboard.get_options()["system"] == "win"
    keyboard.set_options()
    keyboard.set_auto_os(True)
    assert keyboard.get_auto_os()
    for kwargs in ({"system": "ios"}, {"wasd_swap": 1}):
        with pytest.raises(ValueError):
            keyboard.set_options(**kwargs)
    with pytest.raises(ValueError):
        keyboard.set_auto_os(1)
    firmware.send = lambda *a, **kw: None
    with pytest.raises(ProtocolError):
        keyboard.set_options(system="mac")
    with pytest.raises(ProtocolError):
        keyboard.set_auto_os(False)


def test_fn_matrix_validation_and_readback(firmware):
    keyboard = Keyboard(firmware)
    with pytest.raises(ValueError):
        keyboard.write_fn_matrix(bytes(1))
    with pytest.raises(ValueError):
        keyboard.write_fn_matrix(bytes(512), 2)
    firmware.send = lambda *a, **kw: None
    with pytest.raises(ProtocolError, match="Fn matrix"):
        keyboard.write_fn_matrix(bytes(512))


def test_picture_roundtrip_and_single_slot(firmware):
    keyboard = Keyboard(firmware)
    colors = bytes(i % 256 for i in range(378))
    firmware.pictures[4][378:] = bytes([99] * 6)
    keyboard.write_picture(colors, 4)
    assert keyboard.read_picture(4) == colors
    keyboard.set_picture_key(4, 125, 0xABCDEF)
    assert keyboard.read_picture(4) == colors[:375] + bytes.fromhex("abcdef")
    assert firmware.pictures[4][378:] == bytes([99] * 6)
    with pytest.raises(ValueError):
        keyboard.set_picture_key(4, 126, 0)
    with pytest.raises(ValueError):
        keyboard.read_picture(5)
    firmware.send = lambda *a, **kw: None
    with pytest.raises(ProtocolError, match="picture readback"):
        keyboard.write_picture(bytes(378), 4)


def test_partial_picture_is_not_zero_filled(firmware):
    keyboard = Keyboard(firmware)
    exchange = firmware.exchange
    firmware.exchange = lambda p, **kw: (
        bytes(63) if p[0] == 0x8C and p[3] == 5 else exchange(p, **kw)
    )
    with pytest.raises(ProtocolError, match="incomplete custom RGB"):
        keyboard.read_picture()
