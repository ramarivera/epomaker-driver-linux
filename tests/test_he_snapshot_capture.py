"""Schema-7 HE snapshot capture and pure validation."""

import copy
import types

import pytest
from he_snapshot_firmware import snapshot_keyboard

from epomaker_driver.errors import ProtocolError, UnsupportedDevice
from epomaker_driver.he_snapshot import capture, validate


def test_capture_3692_contains_all_profiles_fields_and_macros():
    keyboard, firmware = snapshot_keyboard(3703)
    value = capture(keyboard)
    assert value["schema_version"] == 7
    assert value["identity"]["device_id"] == 3703
    assert len(value["profiles"]) == 4
    assert all(len(profile["matrices"]) == 4 for profile in value["profiles"])
    required = {str(field) for field in (0, 1, 2, 3, 4, 5, 6, 7, 9, 10)}
    assert all(set(profile["fields"]) >= required for profile in value["profiles"])
    assert set(value["macros"]) == {str(slot) for slot in range(256)}
    assert value["macros"]["255"] == (bytes([255]) * 256).hex()
    assert bytes.fromhex(value["side_light"])[0] == 0x88
    assert firmware.profile == 0


def test_capture_2761_omits_unavailable_mac_fn_bank():
    value = capture(snapshot_keyboard(2761)[0])
    assert set(value["fn"]) == {"win"}


def test_capture_2586_has_only_the_windows_fn_bank():
    value = capture(snapshot_keyboard(2586)[0])
    assert set(value["fn"]) == {"win"}


def test_capture_3727_has_three_pictures_and_no_sleep():
    value = capture(snapshot_keyboard(3727)[0])
    assert len(value["pictures"]) == 3
    assert value["sleep"] is None
    assert 1 <= value["debounce"] <= 10
    assert value["side_light"] is None


def test_validate_roundtrip_decodes_all_raw_payloads():
    value = capture(snapshot_keyboard(3692)[0])
    decoded = validate(value)
    assert decoded["schema_version"] == 7
    assert isinstance(decoded["profiles"][0]["matrices"][0], bytes)
    assert isinstance(decoded["profiles"][0]["fields"][7], bytes)
    assert isinstance(decoded["macros"][255], bytes)


@pytest.mark.parametrize("original_profile", [2, 3])
def test_capture_restores_nonzero_original_profile_after_failure(original_profile):
    keyboard, firmware = snapshot_keyboard(3692)
    keyboard.set_profile(original_profile)
    firmware.fail_query = 0xE5
    with pytest.raises(RuntimeError, match="injected capture failure"):
        capture(keyboard)
    assert firmware.profile == original_profile


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["identity"].update(device_id=9999),
        lambda value: value["identity"].update(is_boot=True),
        lambda value: value.update(schema_version=7.0),
        lambda value: value["versions"].update(usb=True),
        lambda value: value["versions"].update(rf=False),
        lambda value: value["versions"].update(usb=-1),
        lambda value: value["versions"].update(rf=0x10000),
    ],
)
def test_validate_rejects_identity_schema_and_version_types(mutate):
    value = capture(snapshot_keyboard(3692)[0])
    mutate(value)
    with pytest.raises(ValueError):
        validate(value)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(light="88" + value["light"][2:]),
        lambda value: value.update(light="zz" * 64),
        lambda value: value.update(options="00" * 63),
        lambda value: value.update(pictures=["00"] + value["pictures"][1:]),
        lambda value: value["fn"].update(win="00"),
        lambda value: value["macros"].update({"255": "00"}),
    ],
)
def test_validate_rejects_malformed_raw_payloads(mutate):
    value = capture(snapshot_keyboard(3692)[0])
    mutate(value)
    with pytest.raises(ValueError):
        validate(value)


def test_validate_rejects_side_light_wrong_opcode_and_length():
    value = capture(snapshot_keyboard(3703)[0])
    wrong_opcode = copy.deepcopy(value)
    wrong_opcode["side_light"] = "87" + wrong_opcode["side_light"][2:]
    with pytest.raises(ValueError):
        validate(wrong_opcode)
    wrong_length = copy.deepcopy(value)
    wrong_length["side_light"] = "88"
    with pytest.raises(ValueError):
        validate(wrong_length)


def test_validate_requires_exact_profile_count():
    value = capture(snapshot_keyboard(3692)[0])
    value["profiles"] = value["profiles"][:3]
    with pytest.raises(ValueError):
        validate(value)
    value = capture(snapshot_keyboard(3727)[0])
    value["profiles"].append(copy.deepcopy(value["profiles"][-1]))
    with pytest.raises(ValueError):
        validate(value)


def test_validate_requires_inactive_fields_when_the_firmware_gate_requires_them():
    value = capture(snapshot_keyboard(3692)[0])
    value["profiles"][0]["fields"].pop("251")
    with pytest.raises(ValueError):
        validate(value)
    value = capture(snapshot_keyboard(3692)[0])
    value["profiles"][0]["fields"].pop("252")
    with pytest.raises(ValueError):
        validate(value)


def test_validate_rejects_extra_top_deadzone_field_below_gate():
    keyboard, firmware = snapshot_keyboard(3692)
    firmware.usb_version = 0x0200
    firmware.rf_version = 0x0300
    value = capture(keyboard)
    assert "251" not in value["profiles"][0]["fields"]
    value["profiles"][0]["fields"]["251"] = "00" * 128
    with pytest.raises(ValueError):
        validate(value)


def test_validate_rejects_missing_macro_255():
    value = capture(snapshot_keyboard(3692)[0])
    del value["macros"]["255"]
    with pytest.raises(ValueError):
        validate(value)


def test_capture_detects_profile_drift():
    keyboard, firmware = snapshot_keyboard(3692)
    firmware.change_profile_on_read = True
    with pytest.raises(ProtocolError, match="profile"):
        capture(keyboard)


def test_capture_detects_firmware_version_drift():
    keyboard, firmware = snapshot_keyboard(3692)
    original_exchange = firmware.exchange
    changed = False

    def drift(exchange_self, command):
        nonlocal changed
        response = original_exchange(command)
        if command[0] == 0x80 and not changed:
            firmware.rf_version = 0x0400
            changed = True
        return response

    firmware.exchange = types.MethodType(drift, firmware)
    with pytest.raises(ProtocolError, match="versions changed"):
        capture(keyboard)


def test_capture_rechecks_identity_before_configuration():
    keyboard, firmware = snapshot_keyboard(3692)
    keyboard.identify()
    firmware.model_id = 3727
    with pytest.raises(UnsupportedDevice):
        capture(keyboard)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["identity"].clear(),
        lambda value: value.update(identity=None),
        lambda value: value.update(versions=None),
        lambda value: value.update(profiles=None),
        lambda value: value["profiles"][0].update(matrices=None),
        lambda value: value["profiles"][0].update(fields=None),
        lambda value: value["profiles"][0]["fields"].update({"01": "00" * 512}),
        lambda value: value["profiles"][0]["fields"].update({"nope": "00" * 512}),
        lambda value: value.update(fn={"mac": value["fn"]["win"]}),
        lambda value: value.update(pictures=value["pictures"][:-1]),
        lambda value: value.update(options="00" + value["options"][2:]),
        lambda value: value.update(auto_os="false"),
        lambda value: value.update(limitations="not-a-list"),
        lambda value: value.update(limitations=[1]),
    ],
)
def test_validate_rejects_malformed_container_shapes(mutate):
    value = capture(snapshot_keyboard(3692)[0])
    mutate(value)
    with pytest.raises(ValueError):
        validate(value)


def test_validate_rejects_non_mapping_snapshot():
    with pytest.raises(ValueError):
        validate([])


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["profiles"].__setitem__(0, {"matrices": [], "fields": {}}),
        lambda value: value["profiles"].__setitem__(
            0, {"matrices": ["00" * 512] * 3, "fields": value["profiles"][0]["fields"]}
        ),
        lambda value: value.update(fn={"win": "00"}),
        lambda value: value.update(pictures=[]),
    ],
)
def test_validate_rejects_wrong_nested_counts(mutate):
    value = capture(snapshot_keyboard(3692)[0])
    mutate(value)
    with pytest.raises(ValueError):
        validate(value)


def test_validate_rejects_nonstring_hex_payload():
    value = capture(snapshot_keyboard(3692)[0])
    value["light"] = None
    with pytest.raises(ValueError):
        validate(value)


def test_validate_rejects_side_light_absent_or_bad_for_side_model():
    value = capture(snapshot_keyboard(3703)[0])
    value["side_light"] = None
    with pytest.raises(ValueError):
        validate(value)


@pytest.mark.parametrize("field", ["sleep", "options"])
def test_validate_rejects_invalid_setting_opcode(field):
    value = capture(snapshot_keyboard(3692)[0])
    if field == "sleep":
        value = capture(snapshot_keyboard(3759)[0])
    value[field] = "00" + value[field][2:]
    with pytest.raises(ValueError):
        validate(value)


def test_validate_rejects_unexpected_sleep_on_wired_model():
    value = capture(snapshot_keyboard(3727)[0])
    value["sleep"] = "91" + "00" * 63
    with pytest.raises(ValueError):
        validate(value)


def test_validate_rejects_invalid_wireless_sleep_shape():
    value = capture(snapshot_keyboard(3759)[0])
    value["sleep"] = "91"
    with pytest.raises(ValueError):
        validate(value)


@pytest.mark.parametrize("debounce", [None, 0, 11, "10", True])
def test_validate_rejects_invalid_wired_debounce(debounce):
    value = capture(snapshot_keyboard(3727)[0])
    value["debounce"] = debounce
    with pytest.raises(ValueError):
        validate(value)


def test_validate_rejects_debounce_on_non_debounce_model():
    value = capture(snapshot_keyboard(3692)[0])
    value["debounce"] = 5
    with pytest.raises(ValueError):
        validate(value)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["profiles"][0]["fields"].pop("10"),
        lambda value: value["profiles"][0]["matrices"].__setitem__(0, "00"),
        lambda value: value["macros"].pop("255"),
        lambda value: value.update(side_light="00"),
        lambda value: value.update(auto_os=1),
    ],
)
def test_validate_rejects_incomplete_or_noncanonical_snapshot(mutate):
    value = capture(snapshot_keyboard(3692)[0])
    mutate(value)
    with pytest.raises(ValueError):
        validate(value)


def test_capture_requires_usb_transport():
    keyboard, _ = snapshot_keyboard(3692)
    keyboard.transport.kind = "bluetooth"
    with pytest.raises(UnsupportedDevice):
        capture(keyboard)


def test_capture_restores_original_profile_after_query_failure():
    keyboard, firmware = snapshot_keyboard(3692)
    keyboard.set_profile(2)
    firmware.fail_query = 0xE5
    with pytest.raises(RuntimeError, match="injected capture failure"):
        capture(keyboard)
    assert firmware.profile == 2


def test_capture_reports_profile_cleanup_failure():
    keyboard, firmware = snapshot_keyboard(3692)
    keyboard.set_profile(1)
    firmware.fail_query = 0xE5
    original_send = firmware.send

    def fail_profile_send(command):
        if command[0] == 4 and command[1] == 1:
            raise RuntimeError("profile restore failed")
        original_send(command)

    firmware.send = fail_profile_send
    with pytest.raises(ProtocolError, match="failed to restore active profile"):
        capture(keyboard)
