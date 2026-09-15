"""Offline preview of vendor Glyph profile configuration records."""

from __future__ import annotations

from collections.abc import Mapping

from .models import data_file, glyph_matrix
from .vendor_actions import encode

TARGETS = ("Main", "Fn Windows", "Fn Mac")


def _int(value, field: str, *, maximum: int = 255, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return value


def _identities(baseline: bytes) -> dict[int, list[int]]:
    function_values = data_file("vendor-action-tables.json").get("functions", {})
    identities: dict[int, list[int]] = {}
    allowed = {
        int.from_bytes(bytes(value), "big") for value in function_values.values() if len(value) == 4
    }
    for slot in range(128):
        value = baseline[slot * 4 : slot * 4 + 4]
        compact = value == bytes((0, 0, value[2], 0))
        identity = value[2] if compact else int.from_bytes(value, "big")
        if compact or identity in allowed:
            identities.setdefault(identity, []).append(slot)
    return identities


def preview(record: Mapping, target: str = "Main") -> dict:
    """Preview a vendor profile record without HID I/O or record mutation."""
    if not isinstance(record, Mapping):
        raise ValueError("record must be an object")
    if target not in TARGETS:
        raise ValueError("target must be Main, Fn Windows, or Fn Mac")
    device = record.get("deviceType")
    if not isinstance(device, Mapping) or type(device.get("id")) is not int or device["id"] != 3059:
        raise ValueError("deviceType.id must be 3059")
    fn = record.get("fn", False)
    if not isinstance(fn, bool):
        raise ValueError("fn must be a boolean")
    if fn != (target != "Main"):
        raise ValueError("record fn flag does not match target")
    actions = record.get("value")
    if not isinstance(actions, list) or len(actions) > 128:
        raise ValueError("value must be a list of at most 128 actions")
    baseline = glyph_matrix()
    identity_slots = _identities(baseline)
    output = bytearray(baseline)
    used: set[int] = set()
    macro_payload_actions: list[int] = []
    for action_index, action in enumerate(actions):
        if not isinstance(action, Mapping):
            raise ValueError(f"action {action_index} must be an object")
        original = _int(action.get("original"), "original", maximum=0x7FFFFFFF)
        slots = identity_slots.get(original)
        if not slots:
            raise ValueError(f"unknown original identity: {original}")
        if len(slots) > 1:
            if "index" not in action:
                raise ValueError(f"duplicate original identity requires index: {original}")
            occurrence = _int(action["index"], "index", maximum=127)
            if occurrence >= len(slots):
                raise ValueError("index is outside the duplicate identity range")
        else:
            occurrence = _int(action.get("index", 0), "index", maximum=127)
            if occurrence != 0:
                raise ValueError("index must be zero for a unique identity")
        slot = slots[occurrence]
        if slot in used:
            raise ValueError(f"multiple actions target slot {slot}")
        used.add(slot)
        output[slot * 4 : slot * 4 + 4] = encode(action)
        if action.get("type") == "ConfigMacro" and "macro" in action:
            macro_payload_actions.append(action_index)
    changed_slots = [
        slot
        for slot in range(128)
        if output[slot * 4 : slot * 4 + 4] != baseline[slot * 4 : slot * 4 + 4]
    ]
    macro_slots = sorted({output[slot * 4 + 2] for slot in range(128) if output[slot * 4] == 9})
    limitations = [
        "Offline byte preview only; hardware applicability and verification are not performed.",
        "Embedded macro data is reported but not converted or applied.",
    ]
    if target != "Main":
        limitations.append(
            "Fn preview uses the normal baseline; OS-specific factory defaults are not applied."
        )
    return {
        "format": "epomaker-glyph-vendor-preview",
        "schema_version": 1,
        "model_id": 3059,
        "target": target,
        "matrix": bytes(output).hex(),
        "changed_slots": changed_slots,
        "macro_slots": macro_slots,
        "macro_payload_actions": sorted(macro_payload_actions),
        "write_ready": False,
        "limitations": limitations,
    }
