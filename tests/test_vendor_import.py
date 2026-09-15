import copy

import pytest

from epomaker_driver import snapshot
from epomaker_driver.device import Keyboard
from epomaker_driver.models import glyph_matrix
from epomaker_driver.vendor_import import plan


def make_snapshot(firmware):
    return snapshot.capture(Keyboard(firmware))


def test_plan_allocates_macro_and_preserves_source(firmware):
    firmware.matrices[1][20:24] = bytes([9, 0, 7, 0])
    firmware.macros[7] = bytearray(256)
    current = make_snapshot(firmware)
    record = {
        "deviceType": {"id": 3059},
        "value": [
            {
                "type": "ConfigMacro",
                "original": 4,
                "macroIndex": 7,
                "macroType": "repeat_times",
                "repeatCount": 1,
                "macro": [
                    {"type": "keyboard", "value": 4, "action": "down"},
                    {"type": "delay", "value": 10},
                ],
            }
        ],
    }
    before = copy.deepcopy(record)
    result = plan(record, current)
    assert result["assignments"] == [{"action_index": 0, "source_slot": 7, "slot": 0}]
    assert result["reserved_slots"] == [7]
    assert result["macros"]["0"] == "0100048a" + "00" * 252
    assert result["write_ready"] is False
    assert record == before


def test_fn_plan_uses_normal_baseline_and_requires_profile_zero(firmware):
    current = make_snapshot(firmware)
    record = {"deviceType": {"id": 3059}, "fn": True, "value": []}
    result = plan(record, current, "Fn Mac")
    assert result["profile"] == 0
    assert result["matrix"] == glyph_matrix().hex()
    with pytest.raises(ValueError):
        plan(record, current, "Fn Mac", profile=1)


def test_fn_plan_reserves_macro_ids_from_all_normal_profiles(firmware):
    firmware.matrices[0][20:24] = bytes([9, 0, 0, 0])
    firmware.macros[0] = bytearray(256)
    current = make_snapshot(firmware)
    result = plan({"deviceType": {"id": 3059}, "fn": True, "value": []}, current, "Fn Windows")
    assert 0 in result["reserved_slots"]


@pytest.mark.parametrize("record", [None, {"deviceType": {"id": 3059}, "value": [None]}])
def test_plan_rejects_bad_record_or_action(firmware, record):
    with pytest.raises(ValueError):
        plan(record, make_snapshot(firmware))


def test_plan_rejects_raw_macro_binding_without_payload(firmware):
    current = make_snapshot(firmware)
    record = {
        "deviceType": {"id": 3059},
        "value": [{"type": "ConfigUnknown", "original": 4, "value": [9, 0, 3, 0]}],
    }
    with pytest.raises(ValueError, match="raw macro"):
        plan(record, current)


def imported_macro():
    return {
        "type": "ConfigMacro",
        "original": 4,
        "macroType": "on_off",
        "repeatCount": 1,
        "macro": [],
    }


@pytest.mark.parametrize("count", [49, 50])
def test_allocator_last_slot_and_exhaustion(firmware, count):
    for slot in range(count):
        firmware.matrices[1][slot * 4 : slot * 4 + 4] = bytes([9, 1, slot, 0])
    current = make_snapshot(firmware)
    before = copy.deepcopy(current)
    record = {"deviceType": {"id": 3059}, "value": [imported_macro()]}
    if count == 50:
        with pytest.raises(ValueError, match="no macro slots"):
            plan(record, current)
    else:
        assert plan(record, current)["assignments"][0]["slot"] == 49
    assert current == before
    assert not firmware.sent


def test_other_fn_os_reserved_and_selected_bank_reusable(firmware):
    firmware.fn[0][0:4] = bytes([9, 1, 0, 0])
    firmware.fn[1][0:4] = bytes([9, 1, 1, 0])
    record = {"deviceType": {"id": 3059}, "fn": True, "value": [imported_macro()]}
    current = make_snapshot(firmware)
    result = plan(record, current, "Fn Mac")
    assert result["reserved_slots"] == [0]
    assert result["assignments"][0]["slot"] == 1


def test_opaque_binding_cannot_borrow_new_payload(firmware):
    record = {
        "deviceType": {"id": 3059},
        "value": [
            imported_macro(),
            {"type": "ConfigUnknown", "original": 5, "value": [9, 1, 0, 0]},
        ],
    }
    with pytest.raises(ValueError, match="raw macro"):
        plan(record, make_snapshot(firmware))


@pytest.mark.parametrize("profile", [True, -1, 3])
def test_invalid_profile(firmware, profile):
    with pytest.raises(ValueError, match="profile"):
        plan({"deviceType": {"id": 3059}, "value": []}, make_snapshot(firmware), profile=profile)


def test_invalid_target_and_missing_actions(firmware):
    current = make_snapshot(firmware)
    with pytest.raises(ValueError, match="target"):
        plan({}, current, "Unknown")
    with pytest.raises(ValueError, match="action list"):
        plan({"deviceType": {"id": 3059}}, current)


def test_non_glyph_snapshot_rejected(firmware):
    firmware.model_id = 2895
    firmware.matrices.append(bytearray(512))
    current = make_snapshot(firmware)
    with pytest.raises(ValueError, match="Glyph"):
        plan({"deviceType": {"id": 3059}, "value": []}, current)


def test_plain_action_import_needs_no_macro_slots(firmware):
    result = plan(
        {
            "deviceType": {"id": 3059},
            "value": [
                {"type": "forbidden", "original": 4},
            ],
        },
        make_snapshot(firmware),
    )
    assert result["macros"] == {}
    assert result["assignments"] == []
