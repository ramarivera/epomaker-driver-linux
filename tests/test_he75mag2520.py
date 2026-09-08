"""Epomaker HE75 Mag (RY5088 model 2520) coverage."""

import hashlib

import pytest
from he_snapshot_firmware import snapshot_keyboard

from epomaker_driver.errors import UnsupportedDevice
from epomaker_driver.models import data_file

HASHES = {
    "defaultMatrix": "0ad2185b921b3e8aec91873426f1af38c60e82e49a2be5c3ae8f736808590ffb",
    "defaultFnMatrix": "1270f37cf7ffcbd3773454547d7013d346dec66ff0486ba11a604867a8f4e9c7",
}


def make_keyboard():
    keyboard, firmware = snapshot_keyboard(2520)
    firmware.matrices.update(
        {(profile, mode): bytes([profile, mode]) * 256 for profile in (2, 3) for mode in range(4)}
    )
    return firmware, keyboard


def test_he75_mag_identity_four_profiles_win_fn_and_matrices():
    firmware, keyboard = make_keyboard()
    matrices = data_file("he60-matrices.json")["2520"]
    assert {
        name: hashlib.sha256(bytes(value)).hexdigest() for name, value in matrices.items()
    } == HASHES
    assert keyboard.identify()["device_id"] == 2520
    assert keyboard.status()["profiles"] == 4
    assert keyboard.read_matrix(profile=3, mode=3)[:2] == bytes((3, 3))
    assert keyboard.read_matrix(profile=0, fn=True, os_mode=0)[:2] == bytes((0, 0))
    with pytest.raises(UnsupportedDevice):
        keyboard.read_matrix(profile=0, fn=True, os_mode=1)
    assert firmware.sent == []


def test_he75_mag_switch_codes_and_catalog_gate():
    firmware, keyboard = make_keyboard()
    keyboard.set_switch_type([1], "磁白轴")
    assert firmware.fields[252][1] == 8
    packet = [packet for packet in firmware.sent if packet[0] == 0x65][-1]
    assert packet[1] == 252 and packet[3] == 1 and packet[8] == 8
    with pytest.raises(ValueError):
        keyboard.set_switch_type([1], "冰玉")


@pytest.mark.parametrize("values", [(0, 0, 10), (64800, 64800, 64800)])
def test_he75_mag_generic_sleep_bounds_and_hidden_word(values):
    firmware, keyboard = make_keyboard()
    firmware.sleep[3] = 0xBEEF
    result = keyboard.set_sleep(*values)
    assert tuple(result[key] for key in ("bluetooth", "dongle", "deep_bluetooth")) == values
    assert firmware.sleep[3] == 0xBEEF


@pytest.mark.parametrize("values", [(-1, 0, 10), (0, 64801, 10), (0, 0, 9)])
def test_he75_mag_sleep_rejects_outside_generic_bounds(values):
    firmware, keyboard = make_keyboard()
    with pytest.raises(ValueError):
        keyboard.set_sleep(*values)
    assert firmware.sent == []


def test_he75_mag_has_no_side_lighting_or_knobs_and_rejects_deep_fn():
    firmware, keyboard = make_keyboard()
    status = keyboard.status()
    assert "side-lighting" not in status["capabilities"]
    assert "knob_slots" not in status
    with pytest.raises(UnsupportedDevice):
        keyboard.get_light(side=True)
    with pytest.raises(UnsupportedDevice):
        keyboard.read_matrix(profile=0, fn=True, os_mode=1)
    assert firmware.sent == []
