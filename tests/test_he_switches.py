import pytest
from test_he import Firmware, keyboard

from epomaker_driver.errors import ProtocolError, UnsupportedDevice
from epomaker_driver.he import HEKeyboard
from epomaker_driver.he_switches import SWITCH_TYPES, resolve_switch


@pytest.mark.parametrize("name,code", SWITCH_TYPES.items())
def test_resolve_switch_names_and_codes(name, code):
    assert resolve_switch(name) == code
    assert resolve_switch(code) == code


@pytest.mark.parametrize("value", [True, False, 6, 34, "unknown", None])
def test_resolve_switch_rejects_unknown_values(value):
    with pytest.raises(ValueError):
        resolve_switch(value)


@pytest.mark.parametrize("model", [2762, 2883, 3664])
def test_switch_type_writes_each_changed_slot_and_preserves_fields(model):
    fw = Firmware(model_id=model)
    base = keyboard(fw, product=0x5029)
    kb = HEKeyboard(base.transport, product_id=0x5029)
    kb.set_switch_type([1, 2], "冰玉")
    writes = [command for command in fw.sent if command[0] == 0x65]
    assert [command[1:5] for command in writes] == [bytes((252, 0, 1, 1)), bytes((252, 0, 2, 1))]
    assert fw.fields[252][1:3] == bytes((33, 33))


def test_switch_type_noop_and_invalid_slots_do_not_write():
    fw = Firmware(model_id=2762)
    kb = HEKeyboard(keyboard(fw, product=0x5029).transport, product_id=0x5029)
    fw.fields[252] = bytes([33]) * 256
    result = kb.set_switch_type([1, 2], 33)
    assert result["changed"] is False
    sent = len(fw.sent)
    for slots in ([], [1, 1], [128], [0, 127, 128]):
        with pytest.raises(ValueError):
            kb.set_switch_type(slots, 33)
    assert len(fw.sent) == sent


def test_h60_and_unknown_catalog_switch_are_rejected_before_writes():
    for model in (3662, 2465):
        fw = Firmware(model_id=model)
        kb = HEKeyboard(keyboard(fw, product=0x5029).transport, product_id=0x5029)
        with pytest.raises(UnsupportedDevice):
            kb.set_switch_type([1], 0)
        assert fw.sent == []


def test_switch_type_readback_damage_is_protocol_error():
    fw = Firmware(model_id=2762)
    fw.corrupt_magnetic_neighbor = True
    kb = HEKeyboard(keyboard(fw, product=0x5029).transport, product_id=0x5029)
    with pytest.raises(ProtocolError, match="switch type readback"):
        kb.set_switch_type([1], 0)


@pytest.mark.parametrize("slots", [[0], [127], [65], [True], [-1], None, "1", list(range(129))])
def test_switch_invalid_physical_slots_never_write(slots):
    fw = Firmware(model_id=2762)
    with pytest.raises(ValueError):
        keyboard(fw, product=0x5029).set_switch_type(slots, 33)
    assert fw.sent == []


@pytest.mark.parametrize("name,code", SWITCH_TYPES.items())
def test_all_switch_codes_write_only_selected_axis(name, code):
    fw = Firmware(model_id=2762)
    fw.fields[252] = bytes([255]) * 128
    before = fw.fields.copy()
    matrices = fw.matrices.copy()
    kb = keyboard(fw, product=0x5029)
    assert resolve_switch(str(code)) == code
    kb.set_switch_type([1], name)
    assert fw.fields[252] == bytes([255, code]) + bytes([255]) * 126
    assert fw.matrices == matrices
    assert all(value == fw.fields[field] for field, value in before.items() if field != 252)
    assert len(fw.sent) == 1
    assert fw.sent[0][0:5] == bytes([0x65, 252, 0, 1, 1])
    assert fw.sent[0][8] == code


@pytest.mark.parametrize("damage", ["matrix", "field", "lost", "profile"])
def test_switch_readback_checks_other_state_and_lost_writes(damage):
    class Damaging(Firmware):
        def send(self, command):
            super().send(command)
            if damage == "matrix":
                self.matrices[0, 3] = bytes(512)
            if damage == "field":
                self.fields[6] = bytes(256)
            if damage == "profile":
                self.profile = 1

    fw = Damaging(model_id=2762)
    fw.drop_magnetic_write = damage == "lost"
    with pytest.raises(ProtocolError):
        keyboard(fw, product=0x5029).set_switch_type([1], 33)
    assert len(fw.sent) == 1


@pytest.mark.parametrize("noop", [False, True])
def test_profile_change_during_baseline_maps_prevents_switch_write(noop):
    class Changing(Firmware):
        def exchange(self, command):
            reply = super().exchange(command)
            if command[0] == 0x8A and command[3] == 7 and command[4] == 3:
                self.profile = 1
            return reply

    fw = Changing(model_id=2762)
    if noop:
        fw.fields[252] = bytes([33]) * 128
    with pytest.raises(ProtocolError, match="before switch write"):
        keyboard(fw, product=0x5029).set_switch_type([1], 33)
    assert fw.sent == []


def test_switch_partial_send_failure_does_not_claim_success():
    fw = Firmware(model_id=2762)
    fw.fail_on_send_index = 1
    with pytest.raises(RuntimeError, match="send failure"):
        keyboard(fw, product=0x5029).set_switch_type([1, 2], 33)
    assert len(fw.sent) == 1
    assert fw.fields[252][1] == 33
    assert fw.fields[252][2] != 33


@pytest.mark.parametrize("selection", [33, "33", "冰玉"])
def test_model_catalog_gate_applies_to_names_and_numeric_codes(selection, monkeypatch):
    from epomaker_driver import he_switches

    monkeypatch.setattr(
        he_switches, "model_by_id", lambda _: {"other": {"supportedSwitchTypes": ["高特"]}}
    )
    fw = Firmware(model_id=2762)
    with pytest.raises(ValueError, match="not listed"):
        keyboard(fw, product=0x5029).set_switch_type([1], selection)
    assert fw.sent == []
