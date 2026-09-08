"""HE75 ei side-light layout is distinct from the older Q model gates."""

import pytest
from he_snapshot_firmware import snapshot_keyboard

from epomaker_driver.errors import ProtocolError


@pytest.mark.parametrize("model", [3518, 3883])
@pytest.mark.parametrize(
    "mode,effect,speed,rgb,rainbow,flag",
    [
        ("wave", 4, 4, 0x123456, False, 7),
        ("wave", 4, 0, 0x123456, True, 8),
        ("solid", 1, 0, 0xFFFFFF, False, 7),
        ("solid", 1, 0, 0xABCDEF, True, 8),
        ("neon", 3, 4, 0xFFFFFF, False, 8),
        ("off", 0, 0, 0xFFFFFF, False, 7),
    ],
)
def test_ei_effect_packets_and_readback(model, mode, effect, speed, rgb, rainbow, flag):
    kb, fw = snapshot_keyboard(model)
    result = kb.set_light(mode, speed=speed, rgb=rgb, rainbow=rainbow, side=True)
    packet = fw.sent[-1]
    assert packet[:5] == bytes([8, effect, speed, 4, flag])
    assert packet[5:8] == (0xFAFFFA if rgb == 0xFFFFFF else rgb).to_bytes(3, "big")
    assert sum(packet[:9]) & 255 == 255
    assert packet[9:] == bytes(55)
    assert result["mode"] == mode and result["speed"] == speed and result["rgb"] == rgb


@pytest.mark.parametrize("model", [3518, 3883])
@pytest.mark.parametrize(
    "mode,kwargs",
    [
        ("breathing", {}),
        ("snake", {}),
        ("wave", {"speed": 5}),
        ("solid", {"speed": 1}),
        ("off", {"brightness": 3}),
        ("neon", {"rainbow": True}),
        ("neon", {"rgb": 0}),
        ("wave", {"option": 1}),
    ],
)
def test_ei_rejects_unadvertised_controls_without_write(model, mode, kwargs):
    kb, fw = snapshot_keyboard(model)
    with pytest.raises(ValueError):
        kb.set_light(mode, side=True, **kwargs)
    assert not fw.sent


def test_q_models_retain_six_effects_and_speed_three():
    kb, fw = snapshot_keyboard(3365)
    kb.set_light("breathing", speed=3, side=True)
    assert fw.sent[-1][1] == 2
    with pytest.raises(ValueError):
        kb.set_light("wave", speed=4, side=True)


def test_ei_failed_readback_is_reported():
    kb, fw = snapshot_keyboard(3518)
    fw.drop_raw_setting = 8
    with pytest.raises(ProtocolError, match="readback"):
        kb.set_light("solid", side=True)
