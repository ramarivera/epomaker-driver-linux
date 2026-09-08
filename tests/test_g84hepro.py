"""Epomaker G84 HE Pro (RY5088 model 4071) coverage."""

import hashlib

import pytest
from test_h60 import _state
from test_he import Firmware, keyboard

from epomaker_driver.errors import UnsupportedDevice
from epomaker_driver.he_settings import plan_update
from epomaker_driver.models import data_file, model_by_id

HASHES = {
    "defaultMatrix": "20c83b83c2882d81c0974e608e16dc3a436d9895ac7c6a85228a7985c35bf262",
    "defaultFnMatrix": "0b9f2f66c68584faad7a72fd6368cb0cc2fc8c67e33bc1a1c1763be5d83283fb",
    "defaultFnMacMatrix": "6187392234efbdf8c241ef8c775281491f7e9e5de39286c09b6cab31e6b21509",
}


def make_keyboard():
    firmware = Firmware(model_id=4071)
    return firmware, keyboard(firmware, product=0x5030)


def test_g84_identity_profiles_fn_and_exact_matrices():
    firmware, kb = make_keyboard()
    matrices = data_file("he60-matrices.json")["4071"]
    assert {
        name: hashlib.sha256(bytes(value)).hexdigest() for name, value in matrices.items()
    } == HASHES
    assert kb.identify()["device_id"] == 4071
    assert kb.status()["profiles"] == 4
    assert kb.read_matrix(profile=3, mode=3)[:2] == bytes((3, 3))
    assert kb.read_matrix(profile=0, fn=True, os_mode=0)[:2] == bytes((0, 0))
    assert kb.read_matrix(profile=0, fn=True, os_mode=1)[:2] == bytes((0, 1))
    assert firmware.sent == []


def test_g84_switch_name_uses_wire_code_133_and_model_gate():
    firmware, kb = make_keyboard()
    kb.set_switch_type([1], "海木比目鱼轴")
    assert firmware.fields[252][1] == 133
    packet = [packet for packet in firmware.sent if packet[0] == 0x65][-1]
    assert packet[1] == 252 and packet[3] == 1 and packet[8] == 133
    with pytest.raises(ValueError):
        kb.set_switch_type([1], "高特")


@pytest.mark.parametrize("values", [(60, 60, 600), (3600, 3600, 3600)])
def test_g84_sleep_bounds_and_hidden_word(values):
    firmware, kb = make_keyboard()
    firmware.sleep[3] = 0xBEEF
    result = kb.set_sleep(*values)
    assert tuple(result[key] for key in ("bluetooth", "dongle", "deep_bluetooth")) == values
    assert firmware.sleep[3] == 0xBEEF


@pytest.mark.parametrize("values", [(59, 60, 600), (60, 3601, 600), (60, 60, 599)])
def test_g84_sleep_rejects_catalog_outside(values):
    firmware, kb = make_keyboard()
    with pytest.raises(ValueError):
        kb.set_sleep(*values)
    assert firmware.sent == []


@pytest.mark.parametrize(
    "usb, value, raw", [(0x200, 3.3, 33), (0x300, 3.3, 330), (0x500, 3.3, 660)]
)
def test_g84_travel_catalog_limit_and_firmware_precision(usb, value, raw):
    result = plan_update(4071, 0, {"travel": value}, _state(usb))
    assert result["changed_fields"] == [0]
    assert bytes.fromhex(result["expected_fields"]["0"])[:2] == raw.to_bytes(2, "little")


def test_g84_deadzone_catalog_limit_and_rf_precision():
    state = _state(0x300)
    state["versions"]["rf"] = 0x500
    result = plan_update(4071, 0, {"deadzone": 0.005}, state)
    assert result["changed_fields"] == [6]
    assert bytes.fromhex(result["expected_fields"]["6"])[:2] == b"\x01\x00"
    with pytest.raises(ValueError):
        plan_update(4071, 0, {"deadzone": 1.005}, state)


def test_g84_rejects_side_and_debounce_features():
    firmware, kb = make_keyboard()
    with pytest.raises(UnsupportedDevice):
        kb.get_light(side=True)
    with pytest.raises(UnsupportedDevice):
        kb.set_debounce(10)


def test_g84_catalog_has_no_knob_or_rapid_trigger_metadata():
    other = model_by_id(4071)["other"]
    assert "knobKeyCodes" not in other
    assert "firePress" not in other["travelSetting"]
    assert "fireLift" not in other["travelSetting"]


@pytest.mark.parametrize("usb", [0x200, 0x300, 0x500])
def test_g84_explicit_deadzone_limit_applies_even_to_old_firmware(usb):
    state = _state(usb)
    with pytest.raises(ValueError):
        plan_update(4071, 0, {"deadzone": 1.1}, state)
    with pytest.raises(ValueError):
        plan_update(4071, 0, {"travel": 3.4}, state)


def test_g84_rapid_trigger_uses_shared_firmware_defaults():
    result = plan_update(
        4071, 0, {"fire": True, "rapid_press": 0.005, "rapid_lift": 2}, _state(0x500)
    )
    assert bytes.fromhex(result["expected_fields"]["2"])[:2] == b"\x01\x00"
    with pytest.raises(ValueError):
        plan_update(
            4071, 0, {"fire": True, "rapid_press": 0.005, "rapid_lift": 2.005}, _state(0x500)
        )
    with pytest.raises(ValueError):
        keyboard(Firmware(model_id=3365), product=0x5030).set_switch_type([1], "海木比目鱼轴")
