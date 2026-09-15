from copy import deepcopy

import pytest

from epomaker_driver.vendor_macros import convert


def test_keyboard_mouse_and_motion_fixture_payload():
    action = {
        "type": "ConfigMacro",
        "macroType": "repeat_times",
        "repeatCount": 2,
        "macro": [
            {"type": "keyboard", "value": 4, "action": "down"},
            {"type": "delay", "value": 10},
            {"type": "mouse_button", "value": -1000, "action": "up"},
            {"type": "delay", "value": 128},
            {"type": "mouse_move", "dx": -3, "dy": 7},
            {"type": "delay", "value": 20},
        ],
    }
    result = convert(action)
    assert result["repeat"] == 2
    assert result["events"] == [
        {"hid_usage": 4, "down": True, "delay_ms": 10},
        {"type": "mouse_button", "button": "left", "down": False, "delay_ms": 128},
        {"type": "mouse_move", "dx": -3, "dy": 7, "delay_ms": 20},
    ]
    assert result["payload"] == "0200048af0008000f900fd071400" + "00" * 242


def test_empty_macro_and_source_immutability():
    action = {"type": "ConfigMacro", "repeatCount": 0, "macro": [], "metadata": {"x": 1}}
    before = deepcopy(action)
    result = convert(action)
    assert result == {"repeat": 0, "events": [], "payload": "00" * 256}
    assert action == before


@pytest.mark.parametrize("value", [-1000, -999, -998, -996, -997])
def test_all_vendor_mouse_button_enums_map_to_semantic_buttons(value):
    action = {
        "type": "ConfigMacro",
        "repeatCount": 1,
        "macro": [
            {"type": "mouse_button", "value": value, "action": "down", "metadata": "ignored"},
            {"type": "delay", "value": 1, "metadata": "ignored"},
        ],
        "metadata": "ignored",
    }
    assert convert(action)["events"][0]["type"] == "mouse_button"


@pytest.mark.parametrize(
    "action",
    [
        None,
        {"type": "keyboard", "repeatCount": 1, "macro": []},
        {"type": "ConfigMacro", "repeatCount": True, "macro": []},
        {"type": "ConfigMacro", "repeatCount": 1, "macro": None},
        {"type": "ConfigMacro", "repeatCount": 1, "macro": [{"type": "delay", "value": 1}]},
        {
            "type": "ConfigMacro",
            "repeatCount": 1,
            "macro": [{"type": "keyboard", "value": 4, "action": "down"}],
        },
        {
            "type": "ConfigMacro",
            "repeatCount": 1,
            "macro": [
                {"type": "keyboard", "value": 4, "action": "hold"},
                {"type": "delay", "value": 1},
            ],
        },
        {
            "type": "ConfigMacro",
            "repeatCount": 1,
            "macro": [
                {"type": "keyboard", "value": 4, "action": "down"},
                {"type": "delay", "value": 0},
            ],
        },
        {
            "type": "ConfigMacro",
            "repeatCount": 1,
            "macro": [
                {"type": "mouse_button", "value": -990, "action": "down"},
                {"type": "delay", "value": 1},
            ],
        },
        {
            "type": "ConfigMacro",
            "repeatCount": 1,
            "macro": [{"type": "mouse_move", "dx": 1, "dy": 2}, {"type": "delay", "value": True}],
        },
        {
            "type": "ConfigMacro",
            "repeatCount": 1,
            "macro": [{"type": "mouse_move", "dx": 128, "dy": 0}, {"type": "delay", "value": 1}],
        },
        {
            "type": "ConfigMacro",
            "repeatCount": 1,
            "macro": [
                {"type": "keyboard", "value": True, "action": "down"},
                {"type": "delay", "value": 1},
            ],
        },
        {
            "type": "ConfigMacro",
            "repeatCount": 1,
            "macro": [{"type": "keyboard", "value": 4}, {"type": "delay", "value": 1}],
        },
        {
            "type": "ConfigMacro",
            "repeatCount": 1,
            "macro": [None, {"type": "delay", "value": 1}],
        },
        {
            "type": "ConfigMacro",
            "repeatCount": 1,
            "macro": [{"type": "other", "value": 1}, {"type": "delay", "value": 1}],
        },
    ],
)
def test_rejects_malformed_vendor_macros(action):
    with pytest.raises(ValueError):
        convert(action)


def test_macro_storage_capacity_is_validated():
    short = [
        {"type": "keyboard", "value": 4, "action": "down"},
        {"type": "delay", "value": 1},
    ] * 127
    assert len(convert({"type": "ConfigMacro", "repeatCount": 1, "macro": short})["payload"]) == 512
    long = short + [
        {"type": "keyboard", "value": 4, "action": "down"},
        {"type": "delay", "value": 1},
    ]
    with pytest.raises(ValueError, match="256"):
        convert({"type": "ConfigMacro", "repeatCount": 1, "macro": long})


@pytest.mark.parametrize(
    "event, delay",
    [
        ({"type": "keyboard", "value": 4, "action": "up"}, {"type": "keyboard", "value": 4}),
        ({"type": "mouse_button", "value": True, "action": "down"}, {"type": "delay", "value": 1}),
        ({"type": "mouse_button", "value": -1000}, {"type": "delay", "value": 1}),
        ({"type": "mouse_button", "value": -1000, "action": "hold"}, {"type": "delay", "value": 1}),
        ({"type": "mouse_move", "dx": 1}, {"type": "delay", "value": 1}),
    ],
)
def test_incomplete_or_mismatched_event_pairs_rejected(event, delay):
    with pytest.raises(ValueError):
        convert({"type": "ConfigMacro", "repeatCount": 1, "macro": [event, delay]})


def test_mouse_action_that_is_not_a_button_is_rejected():
    from epomaker_driver.models import data_file

    table = data_file("vendor-action-tables.json")["mouse"]
    nonbutton = next(
        int(key) for key, raw in table.items() if len(raw) == 4 and raw[2] not in range(240, 245)
    )
    with pytest.raises(ValueError, match="unknown vendor mouse button"):
        convert(
            {
                "type": "ConfigMacro",
                "repeatCount": 1,
                "macro": [
                    {"type": "mouse_button", "value": nonbutton, "action": "down"},
                    {"type": "delay", "value": 1},
                ],
            }
        )
