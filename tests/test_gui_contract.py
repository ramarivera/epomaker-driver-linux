"""GUI metadata must describe the implemented model gates, not catalog guesses."""

import pytest

from epomaker_driver.gui_contract import catalog_contract, ui_descriptor
from epomaker_driver.models import RY5088_IDS, RY6602_IDS, default_matrix

KEYBOARDS = (3059, 2895, 3223, 3152, 1379, 1723, 3727, 3759, *RY5088_IDS, *RY6602_IDS)


@pytest.mark.parametrize("model", KEYBOARDS)
def test_all_keyboard_catalogs_have_usable_slot_maps(model):
    value = catalog_contract(model)
    ui = value["ui"]
    assert ui["matrix_slots"] == 128
    assert ui["macro_slots"] == 256
    assert len(value["matrices"]) == 3
    assert all(len(matrix) == 512 for matrix in value["matrices"])
    assert ui["picture_slots"] == (128 if model in (1379, 1723) else 126)
    assert ui["picture_banks"] == (1 if model in (1379, 1723) else 3 if model == 3727 else 5)
    if model != 3059:
        slots = [g["slot"] for g in value["layout"]["layout"].values()]
        assert sorted(slots) == list(range(128))


@pytest.mark.parametrize("model", [3059, 2895, 3223, 3152, *RY6602_IDS])
def test_modern_catalog_uses_model_default_not_zero_or_glyph(model):
    catalog = catalog_contract(model)
    assert bytes(catalog["matrices"][0]) == default_matrix(model)


@pytest.mark.parametrize(
    "model,profiles,submodes",
    [
        (3727, 2, 4),
        (3759, 2, 4),
        (3518, 2, 4),
        (3613, 2, 4),
        (2376, 4, 4),
        (3417, 4, 4),
        (2895, 4, 1),
        (1379, 3, 1),
    ],
)
def test_profile_and_submode_choices_match_backend(model, profiles, submodes):
    ui = ui_descriptor(model)
    assert ui["profiles"] == profiles
    assert ui["submodes"] == submodes


@pytest.mark.parametrize(
    "model,fields",
    [
        (3059, ["bt", "dongle", "deep_bt", "deep_dongle"]),
        (1379, ["bt", "dongle", "deep_bt", "deep_dongle"]),
        (3417, ["bt", "dongle"]),
        (2376, ["bt", "dongle", "deep_bt"]),
        (3759, ["bt", "dongle", "deep_bt"]),
        (3858, ["bt", "dongle", "deep_bt"]),
        (3727, []),
        (3746, []),
    ],
)
def test_only_public_sleep_fields_are_editable(model, fields):
    ui = ui_descriptor(model)
    assert set(ui["sleep_fields"]) == set(fields)
    assert ("sleep" in ui["controls"]) == bool(fields)
    assert set(ui["sleep_limits"]) == set(fields)


@pytest.mark.parametrize(
    "model,schemas",
    [
        (3059, [2, 3]),
        (2895, [4]),
        (3223, [4]),
        (3152, [4]),
        (3858, [5]),
        (1379, [6]),
        (1723, [6]),
        (3727, [7]),
        (2376, [7]),
    ],
)
def test_backup_schema_choices_match_actual_recovery(model, schemas):
    assert ui_descriptor(model)["backup_schemas"] == schemas


@pytest.mark.parametrize(
    "model,allowed,forbidden",
    [
        (
            2376,
            {"display", "clock", "display_language_toggle", "sleep"},
            {"debounce", "side_lighting", "system_info"},
        ),
        (3727, {"debounce"}, {"sleep", "display", "side_lighting"}),
        (
            2895,
            {"display", "clock", "display_language_toggle", "side_lighting"},
            {"debounce", "system_info"},
        ),
        (1379, {"display", "clock", "system_info", "auto_os"}, {"options", "side_lighting"}),
        (
            1723,
            {"display", "clock", "system_info"},
            {"options", "side_lighting", "display_language_toggle"},
        ),
        (
            3858,
            {"display", "debounce"},
            {"clock", "system_info", "display_language_toggle", "side_lighting"},
        ),
        (3633, {"debounce", "sleep"}, {"display", "side_lighting"}),
    ],
)
def test_controls_match_implemented_commands(model, allowed, forbidden):
    controls = set(ui_descriptor(model)["controls"])
    assert allowed <= controls
    assert not forbidden & controls
