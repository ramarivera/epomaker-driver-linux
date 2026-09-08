"""Epomaker HE75 V2 models 3518 and 3883 coverage."""

import hashlib

import pytest
from he_snapshot_firmware import snapshot_keyboard

from epomaker_driver.models import data_file

HASHES = {
    3518: {
        "defaultMatrix": "d45881fb094dec9e2bf77531243cf458c581ffd29ab5754801f45245b5a9d9fc",
        "defaultFnMatrix": "9a513ac48dba7d2055ee63022daed758be57edff3bef8babf9f48a9ff091d664",
        "defaultFnMacMatrix": "1a76489db6066733fb9f702fa6b5c966708a8a96bf1fc5723555346ad2f06fdf",
    },
    3883: {
        "defaultMatrix": "708a82cc1f19fb6ffe4d82adadb477d371285786e66c7bad8c01e3ee80e1977c",
        "defaultFnMatrix": "490d26e95ab3193b4f8281e21f116ee01844f2a43272dda17248c393704225f1",
        "defaultFnMacMatrix": "cfa660bfc1e98c3c3c370779e219ba50aa75dfc804be32d9177df2128ce25445",
    },
}


def make_keyboard(model_id):
    kb, firmware = snapshot_keyboard(model_id)
    return firmware, kb


@pytest.mark.parametrize("model_id", [3518, 3883])
def test_he75_identity_profiles_fn_and_matrices(model_id):
    firmware, kb = make_keyboard(model_id)
    matrices = data_file("he60-matrices.json")[str(model_id)]
    assert {
        name: hashlib.sha256(bytes(value)).hexdigest() for name, value in matrices.items()
    } == HASHES[model_id]
    assert kb.identify()["device_id"] == model_id
    assert kb.status()["profiles"] == (2 if model_id == 3518 else 4)
    assert kb.read_matrix(profile=0, fn=True, os_mode=1)[:2] == bytes((0, 1))
    if model_id == 3883:
        assert kb.read_matrix(profile=3, mode=3)[:2] == bytes((3, 3))
    else:
        with pytest.raises(ValueError):
            kb.read_matrix(profile=2, mode=0)
    assert firmware.sent == []


@pytest.mark.parametrize(
    ("model_id", "name", "code"),
    [
        (3518, "灭霸轴", 43),
        (3518, "白星", 92),
        (3518, "云玉磁轴", 93),
        (3883, "灭霸轴", 43),
        (3883, "天霸轴", 62),
        (3883, "精灵王轴", 44),
        (3883, "芭比轴", 61),
        (3883, "泰山轴", 86),
    ],
)
def test_he75_switch_codes_and_exact_write(model_id, name, code):
    firmware, kb = make_keyboard(model_id)
    kb.set_switch_type([1], name)
    assert firmware.fields[252][1] == code
    packet = [packet for packet in firmware.sent if packet[0] == 0x65][-1]
    assert packet[1] == 252 and packet[3] == 1 and packet[8] == code


def test_he75_status_exposes_canonical_switch_display_alias():
    _, kb = make_keyboard(3518)
    status = kb.status()
    assert status["switch_types"]["灭霸轴"] == 43
    assert status["switch_display_names"] == {"灭霸轴": "紫星轴"}


@pytest.mark.parametrize(
    "model_id, slots",
    [
        (3518, {"volume-up": 91, "volume-down": 90, "mute": 92}),
        (3883, {"volume-up": 96, "volume-down": 97, "mute": 98}),
    ],
)
def test_he75_knob_slots(model_id, slots):
    _, kb = make_keyboard(model_id)
    assert kb.status()["knob_slots"] == slots


def test_he75_v2_sleep_bounds():
    firmware, kb = make_keyboard(3518)
    firmware.sleep[2:] = [0x1234, 0xBEEF]
    result = kb.set_sleep(60, 3600, 600)
    assert result["deep_bluetooth"] == 600
    assert firmware.sleep[3] == 0xBEEF
    with pytest.raises(ValueError):
        kb.set_sleep(59, 3600, 600)


def test_he75_tmr_sleep_allows_wire_max_and_zero_deep():
    firmware, kb = make_keyboard(3883)
    firmware.sleep[2:] = [0x1234, 0xBEEF]
    result = kb.set_sleep(65535, 65535, 0)
    assert result["deep_bluetooth"] == 0
    assert firmware.sleep[3] == 0xBEEF


def test_he75_tmr_travel_step_is_point_zero_one():
    from test_h60 import _state

    from epomaker_driver.he_settings import plan_update

    result = plan_update(3883, 0, {"travel": 3.3}, _state(0x300))
    assert result["changed_fields"] == [0]
    with pytest.raises(ValueError):
        plan_update(3883, 0, {"travel": 3.305}, _state(0x300))
