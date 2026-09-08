"""Pure HE60 Lite magnetic actuation write planner.

This module only validates state and constructs packets; it never talks to HID.
"""

from __future__ import annotations

from decimal import Decimal

from .magnetic import (
    BYTE_FIELDS,
    READ_PAGES,
    decode_field,
    encode_field,
    key_field,
    top_dead_zone_supported,
    travel_multiplier,
    write_commands,
)

_MODE_NAMES = {0: "normal", 2: "dks", 3: "mt", 4: "tgl_hold", 5: "tgl_dots", 7: "snap"}
_PATCH_FIELDS = {
    "travel": 0,
    "lift": 1,
    "rapid_press": 2,
    "rapid_lift": 3,
    "deadzone": 6,
    "top_deadzone": 251,
}
_KNOWN_FIELDS = set(READ_PAGES)


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{name} must be numeric")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError(f"{name} must be finite")
    return result


def _aligned(value, *, minimum, maximum, name):
    value = _number(value, name)
    if value < Decimal(str(minimum)) or value > Decimal(str(maximum)):
        raise ValueError(f"{name} is outside supported range")
    if (value * 10) % 1:
        raise ValueError(f"{name} must use 0.1 increments")
    return float(value)


def _state_bytes(state):
    fields = state.get("fields")
    if not isinstance(fields, dict):
        raise ValueError("state fields must be a mapping")
    result = {}
    for key, value in fields.items():
        try:
            field = int(key)
        except (TypeError, ValueError):
            raise ValueError("state contains a nonnumeric field") from None
        if key != str(field):
            raise ValueError("state field names must be canonical decimal strings")
        if field not in _KNOWN_FIELDS:
            raise ValueError(f"state contains unknown field {field}")
        if not isinstance(value, str):
            raise ValueError("state field payloads must be hexadecimal strings")
        try:
            payload = bytes.fromhex(value)
        except ValueError:
            raise ValueError(f"field {field} is not hexadecimal") from None
        expected = READ_PAGES[field] * 64
        if len(payload) != expected:
            raise ValueError(f"field {field} has wrong length")
        result[field] = payload
    for field in (0, 1, 6, 7):
        if field not in result:
            raise ValueError(f"state is missing field {field}")
    return result


def _state_versions(state):
    versions = state.get("versions")
    if not isinstance(versions, dict):
        raise ValueError("state versions must be a mapping")
    usb, rf = versions.get("usb"), versions.get("rf")
    for name, value in (("usb", usb), ("rf", rf)):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFF
        ):
            raise ValueError(f"{name} version must be a uint16 or None")
    multiplier = travel_multiplier(usb=usb, rf=rf)
    if "multiplier" in state and (
        type(state["multiplier"]) is not int or state["multiplier"] != multiplier
    ):
        raise ValueError("state multiplier does not match firmware versions")
    return usb, rf, multiplier


def plan_update(model_id, slot, patch, state):
    if type(model_id) is not int or model_id not in (3727, 3759):
        raise ValueError("unsupported HE model")
    if type(slot) is not int or not 0 <= slot <= 127:
        raise ValueError("slot must be 0..127")
    if not isinstance(patch, dict) or not patch:
        raise ValueError("patch must be a nonempty mapping")
    if any(key not in _PATCH_FIELDS and key != "fire" for key in patch):
        raise ValueError("unknown actuation patch field")
    if not isinstance(state, dict):
        raise ValueError("state must be a mapping")
    fields = _state_bytes(state)
    usb, rf, multiplier = _state_versions(state)
    effective_version = rf if rf is not None else usb if usb is not None else 0
    max_travel = 4 if 0 < effective_version < 0x300 else 3.3
    modes = state.get("modes")
    if (
        not isinstance(modes, list)
        or len(modes) != 128
        or any(type(v) is not int or not 0 <= v <= 255 for v in modes)
    ):
        raise ValueError("state modes must contain 128 bytes")
    if bytes(modes) != fields[7]:
        raise ValueError("state modes do not match raw mode field")
    raw_mode = modes[slot]
    mode = raw_mode & 0x7F
    if mode not in _MODE_NAMES:
        raise ValueError("unknown magnetic mode")
    fire = bool(raw_mode & 0x80)
    new_fire = fire if "fire" not in patch else patch["fire"]
    if not isinstance(new_fire, bool):
        raise ValueError("fire must be boolean")
    if ("rapid_press" in patch or "rapid_lift" in patch) and not new_fire:
        raise ValueError("rapid-trigger settings require fire enabled")
    if any(key in patch for key in ("travel", "lift", "deadzone", "top_deadzone")) and mode not in (
        0,
        7,
    ):
        raise ValueError("travel settings are supported only in normal or snap mode")
    if "top_deadzone" in patch and not top_dead_zone_supported(usb=usb, rf=rf):
        raise ValueError("top dead zone is unavailable on this firmware")
    values = {}
    for name, field in _PATCH_FIELDS.items():
        if name not in patch:
            continue
        maximum = max_travel if name in ("travel", "lift") else 2 if name.startswith("rapid") else 1
        if name == "deadzone" and effective_version < 0x300:
            maximum = 4
        values[field] = _aligned(
            patch[name],
            minimum=0.1 if name in ("travel", "lift", "rapid_press", "rapid_lift") else 0,
            maximum=maximum,
            name=name,
        )
    if (new_fire and not fire) or ("rapid_press" in patch or "rapid_lift" in patch):
        for field in (2, 3):
            if field not in fields:
                raise ValueError("rapid-trigger fields are required when enabling fire")
            resulting = values.get(field)
            if resulting is None:
                resulting = decode_field(
                    field, key_field(fields[field], slot, field=field), multiplier=multiplier
                )
            if not 0.1 <= resulting <= 2:
                raise ValueError("provide valid rapid_press and rapid_lift when enabling fire")
    if "lift" in patch:
        deadzone = values.get(
            6, decode_field(6, key_field(fields[6], slot, field=6), multiplier=multiplier)
        )
        if Decimal(str(values[1])) > Decimal(str(max_travel)) - Decimal(str(deadzone)):
            raise ValueError("lift must not exceed maximum travel minus deadzone")
    mode_changed = new_fire != fire
    if mode_changed:
        values[7] = mode | (0x80 if new_fire else 0)
    changed = set(values)
    for field in changed:
        if field not in fields:
            raise ValueError(f"state is missing changed field {field}")
    baseline = {field: key_field(fields[field], slot, field=field) for field in changed}
    actual = {field: encode_field(field, values[field], multiplier=multiplier) for field in changed}
    changed = {field for field in changed if actual[field] != baseline[field]}
    if not changed:
        return {
            "commands": [],
            "expected_fields": {str(k): v.hex() for k, v in fields.items()},
            "changed_fields": [],
        }
    write_values = {field: values[field] for field in changed}
    commands = write_commands(
        write_values,
        key_index=slot,
        multiplier=multiplier,
        mode_changed=mode_changed,
        top_supported=top_dead_zone_supported(usb=usb, rf=rf),
    )
    expected = dict(fields)
    for field in changed:
        offset = slot * (1 if field in BYTE_FIELDS or field in (5, 251) else 2)
        payload = actual[field]
        expected[field] = (
            expected[field][:offset] + payload + expected[field][offset + len(payload) :]
        )
    return {
        "commands": commands,
        "expected_fields": {str(k): v.hex() for k, v in expected.items()},
        "changed_fields": sorted(changed),
    }
