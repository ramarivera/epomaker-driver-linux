from copy import deepcopy

import pytest

from epomaker_driver.models import glyph_matrix
from epomaker_driver.vendor_config import preview


def original_at(slot):
    value = glyph_matrix()[slot * 4 : slot * 4 + 4]
    return value[2] if value == bytes((0, 0, value[2], 0)) else int.from_bytes(value, "big")


def record(*actions, fn=False):
    return {"deviceType": {"id": 3059, "name": "Glyph"}, "fn": fn, "value": list(actions)}


def test_duplicate_identity_occurrences_resolve_to_physical_slots():
    result = preview(
        record(
            {"type": "ConfigUnknown", "original": 40, "index": 0, "value": [1, 2, 3, 4]},
            {"type": "ConfigUnknown", "original": 40, "index": 1, "value": [5, 6, 7, 8]},
        )
    )
    assert result["changed_slots"] == [81, 103]


def test_function_tuple_and_fn_use_normal_baseline():
    result = preview(
        record(
            {"type": "ConfigFunction", "original": original_at(53), "value": [1, 2, 3, 4]},
            fn=True,
        ),
        "Fn Windows",
    )
    assert result["changed_slots"] == [53]
    assert result["matrix"][53 * 8 : 54 * 8] == "01020304"
    assert "normal baseline" in result["limitations"][-1]


@pytest.mark.parametrize(
    "value",
    [
        {"deviceType": {"id": True}, "value": []},
        {"deviceType": {"id": 3059.0}, "value": []},
        {"deviceType": {"id": 3059}, "fn": 1, "value": []},
        {"deviceType": {"id": 3059}, "value": None},
        {"deviceType": {"id": 3059}, "value": [{"type": "forbidden"}]},
        {"deviceType": {"id": 3059}, "value": [{"type": "forbidden", "original": -1}]},
        {"deviceType": {"id": 3059}, "value": [{"type": "forbidden", "original": 42, "index": 2}]},
        {
            "deviceType": {"id": 3059},
            "value": [
                {"type": "ConfigUnknown", "original": 42, "index": 0, "value": [1, 2, 3, 4]},
                {"type": "forbidden", "original": 42, "index": 0},
            ],
        },
    ],
)
def test_invalid_records_rejected(value):
    with pytest.raises(ValueError):
        preview(value)


def test_record_is_not_mutated_and_macro_dependencies_are_reported():
    action = {
        "type": "ConfigMacro",
        "original": 4,
        "macroIndex": 12,
        "macroType": "on_off",
        "macro": {"events": []},
    }
    source = record(action)
    before = deepcopy(source)
    result = preview(source)
    assert source == before
    assert result["macro_payload_actions"] == [0]
    assert result["macro_slots"] == [12]
    assert result["write_ready"] is False


def test_macro_slots_are_unique_when_multiple_actions_use_one_macro():
    result = preview(
        record(
            {"type": "ConfigMacro", "original": 4, "macroIndex": 12, "macroType": "on_off"},
            {"type": "ConfigMacro", "original": 5, "macroIndex": 12, "macroType": "on_off"},
        )
    )
    assert result["macro_slots"] == [12]


def test_empty_fn_actions_are_allowed_and_keep_normal_baseline():
    result = preview(record(fn=True), "Fn Mac")
    assert result["matrix"] == glyph_matrix().hex()
    assert result["changed_slots"] == []


@pytest.mark.parametrize(
    "value",
    [
        None,
        record({"type": "forbidden", "original": 999999}),
        record({"type": "forbidden", "original": 4, "index": 1}),
        record({"type": "forbidden", "original": 4, "index": True}),
    ],
)
def test_preview_rejects_malformed_records_and_identity_resolution(value):
    with pytest.raises(ValueError):
        preview(value)


def test_preview_rejects_unknown_target_and_oversized_action_list():
    with pytest.raises(ValueError):
        preview(record(), "Unknown")
    with pytest.raises(ValueError):
        preview(record(*([{"type": "forbidden", "original": 4}] * 129)))


def test_preview_rejects_duplicate_identity_without_index():
    with pytest.raises(ValueError, match="requires index"):
        preview(record({"type": "forbidden", "original": 40}))


def test_preview_rejects_non_object_actions_and_unknown_target():
    with pytest.raises(ValueError):
        preview(record(None))
    with pytest.raises(ValueError):
        preview(record({"type": "forbidden", "original": 4}), "Linux")
