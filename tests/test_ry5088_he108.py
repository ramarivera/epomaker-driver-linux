"""Epomaker HE108 (RY5088 model 3365) integration coverage."""

import hashlib
from types import MethodType

import pytest
from test_h60 import _state
from test_he import Firmware, keyboard

from epomaker_driver import codec
from epomaker_driver.he_settings import plan_update
from epomaker_driver.models import data_file

HASHES = {
    "defaultMatrix": "256da7e62923fcea2acff80d090785cf8f78e770716a6213ab289fe564ff8668",
    "defaultFnMatrix": "16a734532d26bba34b27e4172ef0340b71a520abe57520dd379a90caba019870",
    "defaultFnMacMatrix": "84e056f0d96321d79a9e2721285e3c16e475a1d83ebfca3911ecd5699d8ab6b4",
}


def make_keyboard():
    firmware = Firmware(model_id=3365)
    firmware.side_light = bytearray(codec.light("solid", side=True))
    exchange = firmware.exchange
    send = firmware.send

    def side_exchange(_self, command):
        if command[0] == 0x88:
            reply = bytearray(firmware.side_light)
            reply[0] = 0x88
            return bytes(reply)
        return exchange(command)

    def side_send(_self, command):
        if command[0] == 8:
            firmware.side_light = bytearray(command)
            firmware.sent.append(command)
            return
        send(command)

    firmware.exchange = MethodType(side_exchange, firmware)
    firmware.send = MethodType(side_send, firmware)
    return firmware, keyboard(firmware, product=0x5030)


def test_he108_identity_status_side_light_and_matrices():
    firmware, kb = make_keyboard()
    matrices = data_file("he60-matrices.json")["3365"]
    assert {
        name: hashlib.sha256(bytes(value)).hexdigest() for name, value in matrices.items()
    } == HASHES
    assert kb.identify()["device_id"] == 3365
    status = kb.status()
    assert status["profiles"] == 4
    assert status["versions"]["rf"] == 0x0500
    assert "side-lighting" in status["capabilities"]
    assert kb.get_light(side=True)["raw"][0] == 0x88
    assert kb.read_matrix(profile=3, mode=3)[:2] == bytes((3, 3))
    assert kb.read_matrix(profile=0, fn=True, os_mode=1)[:2] == bytes((0, 1))
    assert firmware.sent == []


def test_he108_switch_names_use_existing_codes_and_model_gate():
    firmware, kb = make_keyboard()
    kb.set_switch_type([1], "磁玉")
    assert firmware.fields[252][1] == 1
    kb.set_switch_type([1], "万磁王")
    assert firmware.fields[252][1] == 5
    with pytest.raises(ValueError):
        kb.set_switch_type([1], "冰玉")


@pytest.mark.parametrize("values", [(60, 60, 600), (3600, 3600, 3600)])
def test_he108_sleep_catalog_bounds_and_hidden_word(values):
    firmware, kb = make_keyboard()
    firmware.sleep[3] = 0xBEEF
    result = kb.set_sleep(*values)
    assert tuple(result[key] for key in ("bluetooth", "dongle", "deep_bluetooth")) == values
    assert firmware.sleep[3] == 0xBEEF


@pytest.mark.parametrize("values", [(59, 60, 600), (60, 3601, 600), (60, 60, 599), (60, 60, 3601)])
def test_he108_sleep_rejects_outside_catalog_bounds(values):
    firmware, kb = make_keyboard()
    with pytest.raises(ValueError):
        kb.set_sleep(*values)
    assert firmware.sent == []


@pytest.mark.parametrize("usb, value, raw", [(0x300, 3.3, 330), (0x500, 3.3, 660)])
def test_he108_travel_uses_catalog_limit_and_firmware_precision(usb, value, raw):
    state = _state(usb)
    result = plan_update(3365, 0, {"travel": value}, state)
    assert result["changed_fields"] == [0]
    assert bytes.fromhex(result["expected_fields"]["0"])[:2] == raw.to_bytes(2, "little")
    with pytest.raises(ValueError):
        plan_update(3365, 0, {"travel": 3.305}, state)
