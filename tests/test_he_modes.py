import pytest

from epomaker_driver.he_modes import validate_definition


@pytest.mark.parametrize(
    ("mode", "extra", "count"),
    [
        ("normal", {"travel": 2, "lift": 2.8, "deadzone": 0.3}, 1),
        ("dks", {"dynamic_travel": 0.7, "trigger_modes": [1, 2, 3, 4]}, 4),
        ("mt", {"mt_time": 200}, 2),
        ("tgl_hold", {}, 1),
        ("tgl_dots", {}, 1),
    ],
)
def test_validate_definitions(mode, extra, count):
    definition = {"mode": mode, "actions": ["00000400"] * count, **extra}
    result = validate_definition(definition)
    assert result == definition
    assert result is not definition


@pytest.mark.parametrize(
    "definition",
    [
        {"mode": "unknown", "actions": []},
        {"mode": "mt", "actions": ["00000400", "00000500"]},
        {
            "mode": "dks",
            "actions": ["00000400"] * 4,
            "dynamic_travel": 0.4,
            "trigger_modes": [0] * 4,
        },
        {"mode": "tgl_hold", "actions": ["00"]},
        {"mode": "tgl_hold", "actions": ["00000400"], "fire": 1},
        {
            "mode": "normal",
            "actions": ["00000400"],
            "travel": 2,
            "lift": 2.8,
            "deadzone": 0.3,
            "extra": 1,
        },
    ],
)
def test_validate_rejects_bad_definitions(definition):
    with pytest.raises(ValueError):
        validate_definition(definition)


def test_validate_does_not_mutate_nested_trigger_modes():
    definition = {
        "mode": "dks",
        "actions": ["00000400"] * 4,
        "dynamic_travel": 0.7,
        "trigger_modes": [0, 1, 2, 3],
    }
    result = validate_definition(definition)
    result["trigger_modes"][0] = 255
    assert definition["trigger_modes"][0] == 0


def test_dks_dynamic_travel_uses_hundredth_millimeter_precision():
    base = {
        "mode": "dks",
        "actions": ["00000400"] * 4,
        "trigger_modes": [0, 255, 1, 2],
    }
    assert validate_definition({**base, "dynamic_travel": 0.71})["dynamic_travel"] == 0.71
    with pytest.raises(ValueError):
        validate_definition({**base, "dynamic_travel": 0.711})


@pytest.mark.parametrize(
    "definition",
    [
        {
            "mode": "normal",
            "actions": ["00000400"],
            "travel": 2,
            "lift": 2.8,
            "deadzone": 0.3,
            "rapid_press": 0.0,
        },
        {
            "mode": "normal",
            "actions": ["00000400"],
            "travel": 2,
            "lift": 2.8,
            "deadzone": 0.3,
            "top_deadzone": 1.1,
        },
        {
            "mode": "dks",
            "actions": ["00000400"] * 4,
            "dynamic_travel": 0.7,
            "trigger_modes": [0, 1, 2, 256],
        },
        {"mode": "mt", "actions": ["00000400", "00000500"], "mt_time": 9},
        {"mode": "mt", "actions": ["00000400", "00000500"], "mt_time": 1001},
        {"mode": "tgl_hold", "actions": ["00000400"], "rapid_lift": 2.51},
    ],
)
def test_validate_rejects_mode_field_boundaries(definition):
    with pytest.raises(ValueError):
        validate_definition(definition)


@pytest.mark.parametrize("definition", [None, [], {"mode": "tgl_hold", "actions": [123]}])
def test_mode_definition_rejects_invalid_structures(definition):
    with pytest.raises(ValueError):
        validate_definition(definition)
