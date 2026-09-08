"""HE mode definitions and write planning; evidence: docs/magnetic-protocol.md."""

from __future__ import annotations

import copy

from .he_settings import _aligned, _number, plan_update
from .magnetic import encode_field, encode_write, key_field

MODES = {"normal": 0, "dks": 2, "mt": 3, "tgl_hold": 4, "tgl_dots": 5}
ACTION_COUNTS = {"normal": 1, "dks": 4, "mt": 2, "tgl_hold": 1, "tgl_dots": 1}


def validate_definition(definition):
    """Return a validated copy; firmware-dependent constraints are checked by plan_mode."""
    if not isinstance(definition, dict):
        raise ValueError("magnetic mode definition must be a mapping")
    mode = definition.get("mode")
    if not isinstance(mode, str) or mode not in MODES:
        raise ValueError("unknown magnetic mode")
    actions = definition.get("actions")
    if not isinstance(actions, list) or len(actions) != ACTION_COUNTS[mode]:
        raise ValueError(f"actions must contain exactly {ACTION_COUNTS[mode]} entries")
    for action in actions:
        if not isinstance(action, str):
            raise ValueError("actions must be hexadecimal strings")
        try:
            raw = bytes.fromhex(action)
        except ValueError:
            raise ValueError("actions must be hexadecimal strings") from None
        if len(raw) != 4:
            raise ValueError("each action must contain four bytes")
    allowed = {"mode", "actions", "fire", "rapid_press", "rapid_lift"}
    if "fire" in definition and type(definition["fire"]) is not bool:
        raise ValueError("fire must be boolean")
    for name in ("rapid_press", "rapid_lift"):
        if name in definition:
            _aligned(definition[name], minimum=0.1, maximum=2, name=name)
    if mode == "normal":
        allowed |= {"travel", "lift", "deadzone", "top_deadzone"}
        for name in ("travel", "lift", "deadzone"):
            _aligned(
                definition.get(name), minimum=0 if name == "deadzone" else 0.1, maximum=4, name=name
            )
        if "top_deadzone" in definition:
            _aligned(definition["top_deadzone"], minimum=0, maximum=1, name="top_deadzone")
    elif mode == "dks":
        allowed |= {"dynamic_travel", "trigger_modes"}
        dynamic = _number(definition.get("dynamic_travel"), "dynamic_travel")
        if not 0.5 <= dynamic <= 2.5 or (dynamic * 100) % 1:
            raise ValueError("dynamic_travel must be 0.5..2.5 in 0.01 increments")
        trigger = definition.get("trigger_modes")
        if (
            not isinstance(trigger, list)
            or len(trigger) != 4
            or any(type(value) is not int or not 0 <= value <= 255 for value in trigger)
        ):
            raise ValueError("trigger_modes must contain four bytes")
    elif mode == "mt":
        allowed.add("mt_time")
        value = definition.get("mt_time")
        if type(value) is not int or not 10 <= value <= 1000:
            raise ValueError("mt_time must be an integer from 10 through 1000")
    if any(key not in allowed for key in definition):
        raise ValueError("unknown magnetic mode field")
    return copy.deepcopy(definition)


def required_fields(definition, raw_mode):
    fields = {"dks": {4: 256, 10: 512}, "mt": {5: 128}}.get(definition["mode"], {}).copy()
    if definition.get("fire", bool(raw_mode & 0x80)) or any(
        key in definition for key in ("rapid_press", "rapid_lift")
    ):
        fields.update({2: 256, 3: 256})
    return fields


def plan_mode(model_id, slot, definition, state):
    """Plan magnetic fields only; backend writes and verifies action submodes separately."""
    definition = validate_definition(definition)
    current = state["modes"][slot]
    if current & 0x7F not in MODES.values():
        raise ValueError("cannot replace snap or unknown existing magnetic mode")
    target = MODES[definition["mode"]]
    adjusted = copy.deepcopy(state)
    mode_bytes = bytearray.fromhex(adjusted["fields"]["7"])
    mode_bytes[slot] = target | (current & 0x80)
    adjusted["fields"]["7"] = mode_bytes.hex()
    adjusted["modes"][slot] = mode_bytes[slot]
    patch = {
        key: value
        for key, value in definition.items()
        if key
        in ("travel", "lift", "deadzone", "top_deadzone", "fire", "rapid_press", "rapid_lift")
    }
    patch.setdefault("fire", bool(current & 0x80))
    base = plan_update(model_id, slot, patch, adjusted)
    expected = {key: bytes.fromhex(value) for key, value in base["expected_fields"].items()}
    multiplier = state["multiplier"]
    # Mode replacement may retain rapid trigger; verify both resulting thresholds.
    if patch["fire"]:
        for field in (2, 3):
            value = int.from_bytes(key_field(expected[str(field)], slot, field=field), "little")
            if not 0.1 <= value / multiplier <= 2:
                raise ValueError("provide valid rapid_press and rapid_lift for this mode")
    if definition["mode"] == "dks":
        payload = encode_field(4, float(definition["dynamic_travel"]), multiplier=multiplier)
        raw = bytearray(expected["4"])
        raw[slot * 2 : slot * 2 + 2] = payload
        expected["4"] = bytes(raw)
        raw = bytearray(expected["10"])
        for stage, value in enumerate(definition["trigger_modes"]):
            raw[stage * 128 + slot] = value
        expected["10"] = bytes(raw)
    elif definition["mode"] == "mt":
        raw = bytearray(expected["5"])
        # Vendor UI accepts individual milliseconds; Uint8Array truncates ms / 10.
        raw[slot] = definition["mt_time"] // 10
        expected["5"] = bytes(raw)
    changed = {int(key) for key, value in expected.items() if value.hex() != state["fields"][key]}
    order = [field for field in (7, 0, 1, 6, 2, 3, 4, 10, 5, 251) if field in changed]
    commands = []
    for index, field in enumerate(order):
        payload = (
            bytes(expected["10"][stage * 128 + slot] for stage in range(4))
            if field == 10
            else key_field(expected[str(field)], slot, field=field)
        )
        commands.append(
            encode_write(8 if field == 10 else field, slot, payload, commit=index == len(order) - 1)
        )
    return {"commands": commands, "expected_fields": {k: v.hex() for k, v in expected.items()}}
