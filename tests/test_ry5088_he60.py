"""Epomaker HE60 (RY5088 model 3746) backend gates and catalog data."""

import hashlib

import pytest
from test_h60 import _state
from test_he import Firmware, keyboard

from epomaker_driver.he_settings import plan_update
from epomaker_driver.he_switches import model_switch_types
from epomaker_driver.models import data_file

HASHES = {
    "defaultMatrix": "c864e07a8521a009235d8b4632a8cf0f3d3cfd0fa64cee7485cf38b166682aff",
    "defaultFnMatrix": "e7013592b988cbd0b2687bd8716fde7fa3d4fd545dce08209ed4381add3c3a21",
    "defaultFnMacMatrix": "6929e22667a23a22092f0e201cd862b8464926d6c89d5f85a114be1c2ec2ee23",
}


def test_he60_catalog_matrices_and_identity():
    matrices = data_file("he60-matrices.json")["3746"]
    assert {
        name: hashlib.sha256(bytes(value)).hexdigest() for name, value in matrices.items()
    } == HASHES
    fw = Firmware(model_id=3746)
    kb = keyboard(fw, product=0x5029)
    assert kb.identify()["device_id"] == 3746
    assert kb.status()["profiles"] == 4
    assert kb.status()["picture_banks"] == 5


@pytest.mark.parametrize("profile", range(4))
def test_he60_all_four_profiles_and_submodes(profile):
    fw = Firmware(model_id=3746)
    kb = keyboard(fw, product=0x5029)
    assert kb.read_matrix(profile=profile, mode=3)[:2] == bytes((profile, 3))


def test_he60_switch_names_encode_exact_field_252_bytes():
    assert model_switch_types(3746) == {"天青轴": 55, "云玉磁轴": 93}
    fw = Firmware(model_id=3746)
    kb = keyboard(fw, product=0x5029)
    result = kb.set_switch_type([1], "天青轴")
    assert result["axis_type"] == 55
    assert fw.fields[252][1] == 55
    assert fw.sent[-1].startswith(bytes.fromhex("65fc00010100009c37"))

    fw = Firmware(model_id=3746)
    kb = keyboard(fw, product=0x5029)
    kb.set_switch_type([1], "云玉磁轴")
    assert fw.sent[-1].startswith(bytes.fromhex("65fc00010100009c5d"))


def test_he60_rejects_old_switch_names_and_old_model_rejects_new_names():
    with pytest.raises(ValueError):
        keyboard(Firmware(model_id=3746), product=0x5029).set_switch_type([1], "高特")
    with pytest.raises(ValueError):
        keyboard(Firmware(model_id=3664), product=0x5029).set_switch_type([1], "云玉磁轴")


@pytest.mark.parametrize("usb", [0x300, 0x400, 0x500])
def test_he60_travel_3_4_is_allowed_at_firmware_precision(usb):
    result = plan_update(3746, 0, {"travel": 3.4}, _state(usb))
    assert result["changed_fields"] == [0]
    raw = int(3.4 * (10 if usb < 0x300 else 100 if usb < 0x500 else 200))
    assert bytes.fromhex(result["expected_fields"]["0"])[:2] == raw.to_bytes(2, "little")


@pytest.mark.parametrize("usb, value", [(0x300, 0.01), (0x400, 0.01), (0x500, 0.005)])
def test_he60_rapid_minimum_tracks_wire_precision(usb, value):
    state = _state(usb)
    state["modes"][0] = 0x80
    state["fields"]["7"] = (bytes([0x80]) + bytes(127)).hex()
    result = plan_update(3746, 0, {"rapid_press": value}, state)
    assert result["changed_fields"] == [2]


@pytest.mark.parametrize("usb", [0x200, 0x300, 0x500])
def test_he60_catalog_rapid_maximum_is_2_5(usb):
    state = _state(usb)
    state["modes"][0] = 0x80
    state["fields"]["7"] = (bytes([0x80]) + bytes(127)).hex()
    assert plan_update(3746, 0, {"rapid_press": 2.5}, state)["changed_fields"] == [2]


def test_he60_old_firmware_deadzone_maximum_is_four():
    state = _state(0x200)
    assert plan_update(3746, 0, {"deadzone": 4}, state)["changed_fields"] == [6]
    with pytest.raises(ValueError):
        plan_update(3746, 0, {"deadzone": 4.1}, state)


def test_he60_sub_wire_precision_is_rejected_until_usb_0500():
    state = _state(0x400)
    state["modes"][0] = 0x80
    state["fields"]["7"] = (bytes([0x80]) + bytes(127)).hex()
    with pytest.raises(ValueError):
        plan_update(3746, 0, {"rapid_press": 0.005}, state)
