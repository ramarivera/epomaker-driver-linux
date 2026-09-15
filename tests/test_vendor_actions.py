import pytest

import epomaker_driver.vendor_actions as vendor_actions
from epomaker_driver.models import data_file
from epomaker_driver.vendor_actions import encode

TABLES = data_file("vendor-action-tables.json")


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ({"type": "forbidden"}, b"\0\0\0\0"),
        ({"type": "combo", "skey": 2, "key": 4, "key2": 5}, bytes([0, 2, 4, 5])),
        ({"type": "combo", "skey": 99, "key": 0x12345678, "key2": 99}, bytes.fromhex("12345678")),
        ({"type": "ConfigUnknown", "value": [1, 2, 3, 4]}, bytes([1, 2, 3, 4])),
        ({"type": "ConfigFunction", "value": [11, 0, 0, 0]}, bytes([11, 0, 0, 0])),
        ({"type": "ConfigFunction", "key": "播放暂停"}, bytes([3, 0, 205, 0])),
        ({"type": "ConfigMouse", "key": -1000}, bytes([1, 0, 240, 0])),
        ({"type": "ConfigGamepad", "key": "XRIGHT"}, bytes([21, 1, 0, 0])),
        (
            {"type": "ConfigMacro", "macroType": "repeat_times", "macroIndex": 7},
            bytes([9, 0, 7, 0]),
        ),
        ({"type": "ConfigMacro", "macroType": "on_off", "macroIndex": 8}, bytes([9, 1, 8, 0])),
        (
            {"type": "ConfigMacro", "macroType": "touch_repeat", "macroIndex": 9},
            bytes([9, 2, 9, 0]),
        ),
        ({"type": "ConfigSnap", "number": 1, "keyCode": 2}, bytes([22, 1, 2, 0])),
        ({"type": "ConfigMDS", "number": 3, "keyCode": 4}, bytes([23, 3, 4, 0])),
        ({"type": "ConfigMT", "keyCode": 5, "keyCode2": 6, "time": 250}, bytes([24, 5, 6, 25])),
        ({"type": "ConfigControlRecoil", "method": "normal", "gunIndex": 1}, bytes([22, 4, 1, 0])),
        (
            {"type": "ConfigControlRecoil", "method": "switch_keep", "gunIndex": 2},
            bytes([22, 6, 2, 0]),
        ),
        (
            {"type": "ConfigControlRecoil", "method": "switch_toggle", "gunIndex": 3},
            bytes([22, 7, 3, 0]),
        ),
    ],
)
def test_encode_actions(action, expected):
    assert encode({**action, "metadata": "ignored"}) == expected


@pytest.mark.parametrize(
    "action",
    [
        {"type": "nope"},
        {"type": "combo", "skey": 0, "key": 0x100000000, "key2": 0},
        {"type": "combo", "skey": 256, "key": 4, "key2": 0},
        {"type": "ConfigUnknown", "value": [1, 2, 3]},
        {"type": "ConfigFunction", "key": "狙击键"},
        {"type": "ConfigFunction", "key": "missing"},
        {"type": "ConfigFunction", "value": None, "key": "播放暂停"},
        {"type": "ConfigFunction", "key": ["播放暂停"]},
        {"type": "ConfigMouse", "key": -990},
        {"type": "ConfigMouse", "key": "-1000"},
        {"type": "ConfigGamepad", "key": "missing"},
        {"type": "ConfigGamepad", "key": 1},
        {"type": "ConfigMacro", "macroType": "repeat_times"},
        {"type": "ConfigMacro", "macroType": "other", "macroIndex": 1},
        {"type": "ConfigMacro", "macroType": [], "macroIndex": 1},
        {"type": "ConfigSnap", "number": 256, "keyCode": 1},
        {"type": "ConfigMT", "keyCode": 1, "keyCode2": 2, "time": 11},
        {"type": "ConfigMT", "keyCode": 1, "keyCode2": 2, "time": 2560},
        {"type": "ConfigControlRecoil", "method": "other", "gunIndex": 1},
        {"type": "ConfigControlRecoil", "method": {}, "gunIndex": 1},
    ],
)
def test_encode_rejects_malformed_or_unknown_actions(action):
    with pytest.raises(ValueError):
        encode(action)


@pytest.mark.parametrize("action", [None, [], "ConfigMacro", {"type": []}])
def test_encode_rejects_non_objects_and_invalid_types(action):
    with pytest.raises(ValueError):
        encode(action)


def test_vendor_tables_have_only_four_byte_or_empty_entries():
    for table in TABLES.values():
        for value in table.values():
            assert len(value) in (0, 4)


@pytest.mark.parametrize("tables", [None, {"functions": {}, "mouse": {}}])
def test_malformed_vendor_tables_are_rejected(monkeypatch, tables):
    monkeypatch.setattr(vendor_actions, "data_file", lambda _: tables)
    with pytest.raises(ValueError, match="vendor action table"):
        encode({"type": "ConfigFunction", "key": "anything"})
