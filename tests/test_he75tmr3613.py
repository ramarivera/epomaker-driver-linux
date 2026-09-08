"""HE75 V2 TMR (RY5088 model 3613) integration coverage."""

import hashlib

import pytest
from he_snapshot_firmware import snapshot_keyboard
from test_h60 import _state

from epomaker_driver.errors import UnsupportedDevice
from epomaker_driver.he_settings import plan_update
from epomaker_driver.models import data_file

HASHES = {
    "defaultMatrix": "b001e55a9612ef07886dd6b2ee4ad01e29dfe4279a520d9d31382bc0ec8b58ef",
    "defaultFnMatrix": "44a0574915ab5c07f06a50e4f579d89b019bfb0506724ec44615dc1da51b8ed5",
    "defaultFnMacMatrix": "e4f599fbbd372dae750edd0c1ab99a0ae8e0cb154b3e7186bec38958348175ee",
}


def make_keyboard():
    keyboard, firmware = snapshot_keyboard(3613)
    return firmware, keyboard


def test_he75_tmr_identity_two_profiles_fn_and_matrices():
    firmware, keyboard = make_keyboard()
    matrices = data_file("he60-matrices.json")["3613"]
    assert {
        name: hashlib.sha256(bytes(value)).hexdigest() for name, value in matrices.items()
    } == HASHES
    assert keyboard.identify()["device_id"] == 3613
    assert keyboard.status()["profiles"] == 2
    assert keyboard.read_matrix(profile=1, mode=3)[:2] == bytes((1, 3))
    assert keyboard.read_matrix(profile=0, fn=True, os_mode=0)[:2] == bytes((0, 0))
    assert keyboard.read_matrix(profile=0, fn=True, os_mode=1)[:2] == bytes((0, 1))
    with pytest.raises(ValueError):
        keyboard.read_matrix(profile=2, mode=0)
    assert firmware.sent == []


@pytest.mark.parametrize(
    ("name", "code"),
    [("云玉磁轴", 93), ("泰山轴", 86), ("磁玉pro", 2), ("万磁王", 5)],
)
def test_he75_tmr_switch_codes_and_exact_write(name, code):
    firmware, keyboard = make_keyboard()
    keyboard.set_switch_type([1], name)
    assert firmware.fields[252][1] == code
    packet = [packet for packet in firmware.sent if packet[0] == 0x65][-1]
    assert packet[1] == 252 and packet[3] == 1 and packet[8] == code


def test_he75_tmr_switch_gate_and_status_have_no_alias_or_knob_metadata():
    _, keyboard = make_keyboard()
    status = keyboard.status()
    assert "switch_display_names" not in status
    assert "knob_slots" not in status
    with pytest.raises(ValueError):
        keyboard.set_switch_type([1], "灭霸轴")


@pytest.mark.parametrize("values", [(60, 60, 600), (3600, 3600, 3600)])
def test_he75_tmr_sleep_catalog_bounds_and_hidden_word(values):
    firmware, keyboard = make_keyboard()
    firmware.sleep[3] = 0xBEEF
    result = keyboard.set_sleep(*values)
    assert tuple(result[key] for key in ("bluetooth", "dongle", "deep_bluetooth")) == values
    assert firmware.sleep[3] == 0xBEEF


@pytest.mark.parametrize("values", [(59, 60, 600), (60, 3601, 600), (60, 60, 599), (60, 60, 3601)])
def test_he75_tmr_sleep_rejects_outside_catalog_bounds(values):
    firmware, keyboard = make_keyboard()
    with pytest.raises(ValueError):
        keyboard.set_sleep(*values)
    assert firmware.sent == []


def test_he75_tmr_travel_catalog_limit_and_firmware_precision():
    result = plan_update(3613, 0, {"travel": 3.3}, _state(0x300))
    assert result["changed_fields"] == [0]
    assert bytes.fromhex(result["expected_fields"]["0"])[:2] == (330).to_bytes(2, "little")
    with pytest.raises(ValueError):
        plan_update(3613, 0, {"travel": 3.305}, _state(0x300))


def test_he75_tmr_slot_90_is_a_regular_key():
    firmware, keyboard = make_keyboard()
    action = bytes.fromhex("00000400")
    keyboard.set_key(90, action)
    assert keyboard.read_matrix(profile=0, mode=0)[90 * 4 : 90 * 4 + 4] == action


def test_he75_tmr_wrong_usb_product_is_rejected():
    from test_he import Firmware
    from test_he import keyboard as make_usb_keyboard

    keyboard = make_usb_keyboard(Firmware(model_id=3613), product=0x5030)
    with pytest.raises(UnsupportedDevice):
        keyboard.status()
