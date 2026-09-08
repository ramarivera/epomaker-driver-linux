"""Epomaker HE65 Mag (RY5088 model 2376) USB backend coverage."""

import hashlib

import pytest
from he_snapshot_firmware import snapshot_keyboard

from epomaker_driver.errors import UnsupportedDevice
from epomaker_driver.models import data_file

HASHES = {
    "defaultMatrix": "17ab3f0d34a5cad247d4a40e4f593153d03eff23342e312f5372673cbad1773c",
    "defaultFnMatrix": "9d494f055b99b54f970292bde77dd6bfa590eea13c1860726b3685d16fc74771",
    "defaultFnMacMatrix": "9d494f055b99b54f970292bde77dd6bfa590eea13c1860726b3685d16fc74771",
}


def make_keyboard():
    keyboard, firmware = snapshot_keyboard(2376)
    firmware.matrices.update(
        {(profile, mode): bytes([profile, mode]) * 256 for profile in (2, 3) for mode in range(4)}
    )
    return firmware, keyboard


def test_he65_mag_identity_four_profiles_fn_and_exact_matrices():
    firmware, keyboard = make_keyboard()
    matrices = data_file("he60-matrices.json")["2376"]
    assert {
        name: hashlib.sha256(bytes(value)).hexdigest() for name, value in matrices.items()
    } == HASHES
    assert keyboard.identify()["device_id"] == 2376
    assert keyboard.status()["profiles"] == 4
    assert keyboard.read_matrix(profile=3, mode=3)[:2] == bytes((3, 3))
    assert keyboard.read_matrix(profile=0, fn=True, os_mode=0)[:2] == bytes((0, 0))
    assert keyboard.read_matrix(profile=0, fn=True, os_mode=1)[:2] == bytes((0, 1))
    assert firmware.sent == []


def test_he65_mag_knob_slots_and_nonreplaceable_switch_gate():
    _, keyboard = make_keyboard()
    status = keyboard.status()
    assert status["knob_slots"] == {"volume-up": 90, "volume-down": 91, "mute": 92}
    with pytest.raises(UnsupportedDevice):
        keyboard.set_switch_type([1], "高特")


@pytest.mark.parametrize("values", [(0, 0, 10), (64800, 64800, 64800)])
def test_he65_mag_generic_sleep_bounds_and_hidden_word(values):
    firmware, keyboard = make_keyboard()
    firmware.sleep[3] = 0xBEEF
    result = keyboard.set_sleep(*values)
    assert tuple(result[key] for key in ("bluetooth", "dongle", "deep_bluetooth")) == values
    assert firmware.sleep[3] == 0xBEEF
