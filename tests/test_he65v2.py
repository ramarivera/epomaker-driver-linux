"""Epomaker HE65 V2 (RY5088 model 3417) coverage."""

import hashlib

import pytest
from test_he import Firmware, keyboard

from epomaker_driver.errors import UnsupportedDevice
from epomaker_driver.models import data_file, model_by_id

HASHES = {
    "defaultMatrix": "21708b469ba9fa931202b47ac4bd70e2fee26b16ab855df20f7e7dfd52e30c9b",
    "defaultFnMatrix": "9c5d518a93a669bb815134275386180dde9d9d46da2f8878784e7b715ae49fad",
    "defaultFnMacMatrix": "32ca4cb7bcea56cb730f476ece616b91b5fd89da69f646112e6793adafc5d834",
}


def make_keyboard():
    firmware = Firmware(model_id=3417)
    return firmware, keyboard(firmware, product=0x5030)


def test_he65_identity_profiles_fn_and_matrices():
    firmware, kb = make_keyboard()
    matrices = data_file("he60-matrices.json")["3417"]
    assert {
        name: hashlib.sha256(bytes(value)).hexdigest() for name, value in matrices.items()
    } == HASHES
    assert kb.identify()["device_id"] == 3417
    assert kb.status()["profiles"] == 4
    assert kb.read_matrix(profile=3, mode=3)[:2] == bytes((3, 3))
    assert kb.read_matrix(profile=0, fn=True, os_mode=0)[:2] == bytes((0, 0))
    assert kb.read_matrix(profile=0, fn=True, os_mode=1)[:2] == bytes((0, 1))
    assert firmware.sent == []


@pytest.mark.parametrize(("name", "code"), [("云玉磁轴", 93), ("机械轴", 7)])
def test_he65_switch_codes_and_exact_write(name, code):
    firmware, kb = make_keyboard()
    kb.set_switch_type([1], name)
    assert firmware.fields[252][1] == code
    packet = [packet for packet in firmware.sent if packet[0] == 0x65][-1]
    assert packet[1] == 252 and packet[3] == 1 and packet[8] == code


def test_he65_switch_model_gate_rejects_unlisted_global_type():
    _, kb = make_keyboard()
    with pytest.raises(ValueError):
        kb.set_switch_type([1], "高特")


def test_he65_two_public_sleep_timers_preserve_both_hidden_words():
    firmware, kb = make_keyboard()
    firmware.sleep[2:] = [0x1234, 0xBEEF]
    result = kb.set_sleep(0, 64800)
    assert result == {"bluetooth": 0, "dongle": 64800}
    assert firmware.sleep[2:] == [0x1234, 0xBEEF]
    assert kb.get_sleep() == {"bluetooth": 0, "dongle": 64800}


@pytest.mark.parametrize("args", [(0, 0, 1), (0, 0, None, 1)])
def test_he65_rejects_supplied_deep_timers(args):
    _, kb = make_keyboard()
    with pytest.raises(ValueError):
        kb.set_sleep(*args)


@pytest.mark.parametrize("values", [(-1, 0), (0, 64801)])
def test_he65_sleep_bounds(values):
    _, kb = make_keyboard()
    with pytest.raises(ValueError):
        kb.set_sleep(*values)


def test_he65_no_side_light_or_debounce():
    _, kb = make_keyboard()
    with pytest.raises(UnsupportedDevice):
        kb.get_light(side=True)
    with pytest.raises(UnsupportedDevice):
        kb.set_debounce(10)


def test_he65_knob_metadata_lists_the_three_verified_inputs():
    assert model_by_id(3417)["other"]["knobKeyCodes"] == [
        "AudioVolumeDown",
        "AudioVolumeMute",
        "AudioVolumeUp",
    ]
