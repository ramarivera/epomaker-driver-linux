"""RY5088 Q-layout side lighting through the real USB transport wrapper."""

from types import MethodType

import pytest
from test_he import Firmware, keyboard

from epomaker_driver import codec
from epomaker_driver.errors import ProtocolError, UnsupportedDevice


@pytest.fixture(params=[2586, 2870])
def side_keyboard(request):
    firmware = Firmware(model_id=request.param)
    firmware.side_light = bytearray(codec.light("solid", side=True))
    exchange = firmware.exchange
    send = firmware.send

    def side_exchange(_self, command):
        if command[0] == 0x88:
            return bytes([0x88]) + bytes(firmware.side_light[1:])
        return exchange(command)

    def side_send(_self, command):
        if command[0] == 8:
            firmware.sent.append(command)
            firmware.side_light = bytearray(command)
            return
        send(command)

    firmware.exchange = MethodType(side_exchange, firmware)
    firmware.send = MethodType(side_send, firmware)
    return keyboard(firmware, product=0x502D), firmware


@pytest.mark.parametrize("mode", tuple(codec.SIDE_MODES))
def test_q_side_effects_roundtrip_and_exact_packet(side_keyboard, mode):
    keyboard_instance, firmware = side_keyboard
    options = {
        "rgb": 0xFFFFFF if mode in ("off", "neon") else 0x123456,
        "rainbow": False if mode in ("off", "neon") else True,
    }
    brightness = 4 if mode == "off" else 2
    speed = 0 if mode in ("off", "solid") else 3
    value = keyboard_instance.set_light(
        mode, side=True, brightness=brightness, speed=speed, **options
    )
    command = firmware.sent[-1]
    expected = codec.light(
        mode,
        side=True,
        **options,
        brightness=brightness,
        speed=speed,
        option=0,
        side_speed_max=3,
        normal=7,
        dazzle=8,
    )
    expected_response = bytes([0x88]) + expected[1:]
    assert command == expected
    assert value["raw"] == list(expected_response)
    assert value["mode"] == mode


def test_q_side_rejects_speed_and_unsupported_rgb_before_write(side_keyboard):
    keyboard_instance, firmware = side_keyboard
    with pytest.raises(ValueError):
        keyboard_instance.set_light("wave", side=True, speed=4)
    with pytest.raises(ValueError):
        keyboard_instance.set_light("neon", side=True, rgb=0x123456)
    with pytest.raises(ValueError):
        keyboard_instance.set_light("wave", side=True, rainbow=1)
    assert not firmware.sent


def test_q_side_readback_failure_is_reported(side_keyboard):
    keyboard_instance, firmware = side_keyboard
    original = firmware.send

    def corrupt(_self, command):
        original(command)
        if command[0] == 8:
            firmware.side_light[5] ^= 1

    firmware.send = MethodType(corrupt, firmware)
    with pytest.raises(ProtocolError, match="side-lighting readback"):
        keyboard_instance.set_light("wave", side=True)


@pytest.mark.parametrize("model_id", [3727, 3759, 3662, 3664, 2762, 2883])
def test_side_layout_is_gated_to_q_models(model_id):
    firmware = Firmware(model_id=model_id)
    keyboard_instance = keyboard(
        firmware,
        product=0x5029
        if model_id not in (3727, 3759)
        else (0x502C if model_id == 3727 else 0x502E),
    )
    with pytest.raises(UnsupportedDevice):
        keyboard_instance.get_light(side=True)
    with pytest.raises(UnsupportedDevice):
        keyboard_instance.set_light("wave", side=True)
    assert not firmware.sent


@pytest.mark.parametrize(
    "options",
    [
        {"mode": "wave", "option": 1},
        {"mode": "solid", "speed": 1},
        {"mode": "off", "brightness": 1},
        {"mode": "off", "rgb": 0},
        {"mode": "off", "rainbow": True},
    ],
)
def test_side_controls_match_catalog(side_keyboard, options):
    kb, fw = side_keyboard
    with pytest.raises(ValueError):
        kb.set_light(side=True, **options)
    assert fw.sent == []


def test_side_status_and_cli_use_real_product_gate(side_keyboard, monkeypatch, capsys):
    from epomaker_driver import cli
    from epomaker_driver.discovery import DeviceInfo

    kb, fw = side_keyboard
    status = kb.status()
    assert "side-lighting" in status["capabilities"]
    assert status["side_light"]["mode"] == "solid"
    assert set(status["switch_types"].values()) == set(range(6))
    info = DeviceInfo("/dev/side", "Keyboard", 3, 0x3151, 0x502D, b"", "usb", 0)

    class Opened:
        def __enter__(self):
            return kb.transport

        def __exit__(self, *_):
            return None

    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: Opened())
    assert cli.main(["--device", info.path, "light", "wave", "--side", "--speed", "3"]) == 0
    capsys.readouterr()
    assert fw.sent[-1][0] == 8


def test_unknown_side_effect_never_writes(side_keyboard):
    kb, fw = side_keyboard
    with pytest.raises(ValueError, match="unsupported HE side"):
        kb.set_light("reactive", side=True)
    assert fw.sent == []


def test_raw_side_command_cannot_bypass_model_gate():
    fw = Firmware(model_id=3662)
    kb = keyboard(fw, product=0x5029)
    with pytest.raises(UnsupportedDevice, match="side lighting"):
        kb._write([codec.light("wave", side=True)])
    assert fw.sent == []
