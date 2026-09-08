"""Catalog overrides and firmware defaults from vendor magnetic UI getters."""

import pytest
from test_h60 import _state

from epomaker_driver.he_settings import plan_update


@pytest.mark.parametrize(
    "usb,minimum,step,raw", [(0x200, 0.1, 0.1, 1), (0x300, 0.01, 0.01, 1), (0x500, 0.01, 0.005, 2)]
)
def test_missing_rapid_step_uses_firmware_default(usb, minimum, step, raw):
    patch = {"fire": True, "rapid_press": minimum, "rapid_lift": minimum + step}
    result = plan_update(2520, 1, patch, _state(usb))
    assert bytes.fromhex(result["expected_fields"]["2"])[2:4] == raw.to_bytes(2, "little")
    with pytest.raises(ValueError):
        plan_update(2520, 1, {**patch, "rapid_press": 0.005}, _state(usb))


@pytest.mark.parametrize("usb", [0x300, 0x500])
def test_he75_travel_deadzone_catalog_steps_and_maximum(usb):
    result = plan_update(2520, 1, {"travel": 4, "deadzone": 1}, _state(usb))
    scale = 100 if usb == 0x300 else 200
    assert bytes.fromhex(result["expected_fields"]["0"])[2:4] == (4 * scale).to_bytes(2, "little")
    for patch in [{"travel": 2.01}, {"travel": 4.02}, {"deadzone": 0.01}, {"deadzone": 1.02}]:
        with pytest.raises(ValueError):
            plan_update(2520, 1, patch, _state(usb))


@pytest.mark.parametrize("model", [3746, 3365, 4071, 3883, 3613, 2520])
def test_old_firmware_four_mm_precedes_catalog_maximum(model):
    result = plan_update(model, 1, {"travel": 4, "deadzone": 4}, _state(0x200))
    assert bytes.fromhex(result["expected_fields"]["0"])[2:4] == b"\x28\x00"
    assert bytes.fromhex(result["expected_fields"]["6"])[2:4] == b"\x28\x00"
    for patch in [{"travel": 4.1}, {"deadzone": 4.1}]:
        with pytest.raises(ValueError):
            plan_update(model, 1, patch, _state(0x200))


def test_rf_version_selects_old_firmware_ui_limits_over_new_usb():
    state = _state(0x500)
    state["versions"]["rf"] = 0x200
    result = plan_update(4071, 1, {"travel": 4, "deadzone": 4}, state)
    assert bytes.fromhex(result["expected_fields"]["0"])[2:4] == b"\x28\x00"
