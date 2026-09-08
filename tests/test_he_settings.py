import pytest

from epomaker_driver.he_settings import plan_update


def state(*, mode=0, usb=0x400, rf=None, travel=2.0, lift=0.5, deadzone=0.2):
    multiplier = 10 if (rf or usb or 0) < 0x300 else 100 if (rf or usb or 0) < 0x500 else 200

    def u16(value):
        raw = int(value * multiplier)
        return raw.to_bytes(2, "little")

    fields = {str(field): bytes(256).hex() for field in (0, 1, 2, 3, 4, 6)}
    fields["0"] = (u16(travel) + bytes(254)).hex()
    fields["1"] = (u16(lift) + bytes(254)).hex()
    fields["6"] = (u16(deadzone) + bytes(254)).hex()
    fields["2"] = (u16(0.5) + bytes(254)).hex()
    fields["3"] = (u16(0.6) + bytes(254)).hex()
    fields["7"] = (bytes((mode,)) + bytes(127)).hex()
    fields["251"] = (bytes((20,)) + bytes(127)).hex()
    return {
        "fields": fields,
        "modes": [mode] + [0] * 127,
        "versions": {"usb": usb, "rf": rf},
    }


def test_exact_travel_command_and_expected_whole_array():
    current = state()
    result = plan_update(3759, 0, {"travel": 2.1}, current)
    assert result["changed_fields"] == [0]
    assert len(result["commands"]) == 1
    assert result["commands"][0] == bytes.fromhex("6500000001000099d2") + bytes(55)
    assert len(result["expected_fields"]["0"]) == 512
    assert bytes.fromhex(result["expected_fields"]["0"])[:2] == (210).to_bytes(2, "little")


def test_h60_uses_precision_step_from_firmware_version():
    current = state(usb=0x400, travel=2.0)
    result = plan_update(3662, 0, {"travel": 2.02}, current)
    assert result["changed_fields"] == [0]
    assert bytes.fromhex(result["expected_fields"]["0"])[:2] == (202).to_bytes(2, "little")
    with pytest.raises(ValueError):
        plan_update(3759, 0, {"travel": 2.01}, current)


def test_noop_preserves_all_fields_and_emits_no_commands():
    current = state()
    result = plan_update(3727, 0, {"travel": 2.0}, current)
    assert result["commands"] == []
    assert result["changed_fields"] == []
    assert result["expected_fields"] == current["fields"]


@pytest.mark.parametrize("mode", [0, 7])
def test_fire_toggle_preserves_low_mode_and_rapid_values(mode):
    current = state(mode=mode)
    current["modes"][0] = mode
    result = plan_update(3759, 0, {"fire": True}, current)
    assert result["changed_fields"] == [7]
    assert result["commands"][0][1:5] == bytes((7, 0, 0, 1))
    assert bytes.fromhex(result["expected_fields"]["2"]) == bytes.fromhex(current["fields"]["2"])


def test_rapid_change_requires_fire_and_is_ordered_after_mode():
    current = state(mode=2)
    current["modes"][0] = 0x82
    current["fields"]["7"] = (bytes((0x82,)) + bytes(127)).hex()
    result = plan_update(3759, 0, {"rapid_press": 0.7}, current)
    assert result["changed_fields"] == [2]
    assert result["commands"][-1][4] == 1
    with pytest.raises(ValueError):
        plan_update(3759, 0, {"rapid_press": 0.7}, state(mode=2))


def test_dks_rejects_travel_but_allows_rapid_and_unknown_modes_reject():
    current = state(mode=2)
    current["modes"][0] = 0x82
    current["fields"]["7"] = (bytes((0x82,)) + bytes(127)).hex()
    with pytest.raises(ValueError):
        plan_update(3759, 0, {"travel": 1.0}, current)
    unknown = state(mode=6)
    unknown["modes"][0] = 6
    with pytest.raises(ValueError):
        plan_update(3759, 0, {"fire": True}, unknown)


@pytest.mark.parametrize(
    "key,value",
    [
        ("travel", -0.1),
        ("travel", 0),
        ("travel", 3.4),
        ("lift", 0),
        ("rapid_press", 0),
        ("rapid_press", 2.1),
        ("deadzone", 1.1),
    ],
)
def test_bounds(key, value):
    with pytest.raises(ValueError):
        plan_update(3759, 0, {key: value}, state())


def test_old_firmware_allows_four_mm_deadzone_and_top_gate_rejects():
    old = state(usb=0x200)
    assert plan_update(3727, 0, {"deadzone": 3.9}, old)["changed_fields"] == [6]
    with pytest.raises(ValueError):
        plan_update(3727, 0, {"travel": 3.4}, state(usb=0, rf=None))
    with pytest.raises(ValueError):
        plan_update(3759, 0, {"top_deadzone": 0.5}, state(usb=0x300))


def test_rf_version_controls_scaling_over_usb_version():
    current = state(usb=0x200, rf=0x400)
    assert plan_update(3759, 0, {"travel": 2.1}, current)["changed_fields"] == [0]


def test_lift_must_fit_travel_minus_deadzone():
    with pytest.raises(ValueError):
        plan_update(3759, 0, {"lift": 3.2}, state(travel=2, deadzone=0.2))
    assert plan_update(3759, 0, {"lift": 3.0}, state(travel=2, deadzone=0.2))["changed_fields"] == [
        1
    ]


@pytest.mark.parametrize("patch", [{}, {"wat": 1}, {"fire": 1}])
def test_patch_validation(patch):
    with pytest.raises(ValueError):
        plan_update(3759, 0, patch, state())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.update(fields=None),
        lambda s: s["fields"].update({"wat": "00" * 256}),
        lambda s: s["fields"].update({"0": "zz"}),
        lambda s: s["fields"].update({"0": "00"}),
        lambda s: s["fields"].pop("7"),
        lambda s: s.update(versions=None),
        lambda s: s["versions"].update({"usb": True}),
        lambda s: s.update(modes=[0]),
    ],
)
def test_malformed_state_rejected(mutate):
    current = state()
    mutate(current)
    with pytest.raises(ValueError):
        plan_update(3759, 0, {"travel": 1.0}, current)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "x", "2.1", True, 1.01])
def test_numeric_validation(value):
    with pytest.raises(ValueError):
        plan_update(3759, 0, {"travel": value}, state())


def test_missing_or_invalid_rapid_state_rejected_when_enabling_fire():
    current = state()
    current["fields"].pop("2")
    with pytest.raises(ValueError):
        plan_update(3759, 0, {"fire": True}, current)


def test_invalid_existing_rapid_values_can_be_repaired_together():
    current = state()
    current["fields"]["2"] = (b"\x00\x00" + bytes(254)).hex()
    current["fields"]["3"] = (b"\x00\x00" + bytes(254)).hex()
    current["modes"][0] = 0x80
    current["fields"]["7"] = (b"\x80" + bytes(127)).hex()
    result = plan_update(3759, 0, {"rapid_press": 0.5, "rapid_lift": 0.6}, current)
    assert result["changed_fields"] == [2, 3]


def test_mode_array_must_match_field7_raw_byte():
    current = state()
    current["fields"]["7"] = (b"\x80" + bytes(127)).hex()
    with pytest.raises(ValueError):
        plan_update(3759, 0, {"travel": 2.1}, current)


def test_unknown_and_nonstring_field_payloads_rejected():
    current = state()
    current["fields"]["11"] = (bytes(256)).hex()
    with pytest.raises(ValueError):
        plan_update(3759, 0, {"travel": 1.0}, current)
    current = state()
    current["fields"]["0"] = bytes(256)
    with pytest.raises(ValueError):
        plan_update(3759, 0, {"travel": 1.0}, current)


def test_multiplier_is_derived_when_state_omits_it_and_valid_lift_passes():
    current = state()
    result = plan_update(3759, 0, {"lift": 0.6}, current)
    assert result["changed_fields"] == [1]
    current = state()
    current["fields"]["2"] = (b"\xff\xff" + bytes(254)).hex()
    with pytest.raises(ValueError):
        plan_update(3759, 0, {"fire": True}, current)


@pytest.mark.parametrize("model,slot", [(1, 0), (3759, -1), (3759, 128)])
def test_model_and_slot_validation(model, slot):
    with pytest.raises(ValueError):
        plan_update(model, slot, {"travel": 1.0}, state())


def test_remaining_state_validation_branches():
    with pytest.raises(ValueError):
        plan_update(3759, 0, {"travel": 1.0}, None)
    current = state()
    current["fields"]["01"] = current["fields"].pop("0")
    with pytest.raises(ValueError):
        plan_update(3759, 0, {"travel": 1.0}, current)
    current = state()
    current["multiplier"] = 10
    with pytest.raises(ValueError):
        plan_update(3759, 0, {"travel": 1.0}, current)
    current = state()
    current["fields"].pop("251", None)
    with pytest.raises(ValueError):
        plan_update(3759, 0, {"top_deadzone": 0.5}, current)


def test_decimal_quantum_compares_against_raw_baseline():
    current = state(travel=2.0)
    current["fields"]["0"] = (b"\xe5\x00" + bytes(254)).hex()
    # Correct the legacy binary-floating-point result of 229 to exact 230.
    result = plan_update(3759, 0, {"travel": 2.3}, current)
    assert result["commands"][0][8:10] == b"\xe6\x00"
    current["fields"]["0"] = result["expected_fields"]["0"]
    assert plan_update(3759, 0, {"travel": 2.3}, current)["commands"] == []


def test_full_ordered_update_has_one_final_commit_and_preserves_input():
    current = state()
    baseline = current["fields"].copy()
    result = plan_update(
        3759,
        0,
        {
            "fire": True,
            "travel": 1.2,
            "lift": 1.3,
            "deadzone": 0.3,
            "rapid_press": 0.2,
            "rapid_lift": 0.4,
            "top_deadzone": 0.5,
        },
        current,
    )
    assert result["commands"] == [
        bytes.fromhex(prefix) + bytes(55)
        for prefix in (
            "650700000000009380",
            "650000000000009a78",
            "650100000000009982",
            "65060000000000941e",
            "650200000000009814",
            "650300000000009728",
            "65fb00000100009e32",
        )
    ]
    assert current["fields"] == baseline
    for field in baseline:
        width = 1 if field in ("7", "251") else 2
        assert (
            bytes.fromhex(result["expected_fields"][field])[width:]
            == bytes.fromhex(baseline[field])[width:]
        )
