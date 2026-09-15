"""Plan an offline Glyph vendor configuration import."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

from . import snapshot
from .vendor_actions import encode
from .vendor_config import TARGETS, preview
from .vendor_macros import convert


def _target_fn(target: str) -> bool:
    if target not in TARGETS:
        raise ValueError("target must be Main, Fn Windows, or Fn Mac")
    return target != "Main"


def plan(
    record: Mapping, current_snapshot: Mapping, target: str = "Main", profile: int = 0
) -> dict:
    """Build a deterministic, no-I/O import plan for one Glyph target."""
    fn = _target_fn(target)
    if type(profile) is not int or not 0 <= profile <= 2:
        raise ValueError("profile must be an integer from 0 to 2")
    if fn and profile != 0:
        raise ValueError("Fn imports require profile 0")
    matrices, fn_matrices, _macros, _settings, _sleep, _pictures = snapshot.validate(
        current_snapshot
    )
    if current_snapshot["identity"]["device_id"] != 3059 or len(matrices) != 3:
        raise ValueError("current snapshot must contain three Glyph profiles")
    selected_fn_key = "win" if target == "Fn Windows" else "mac"
    reserved: set[int] = set()
    for index, matrix in enumerate(matrices):
        if fn or index != profile:
            reserved |= set(snapshot.macro_slots([matrix]))
    for key, matrix in fn_matrices.items():
        if not fn or key != selected_fn_key:
            reserved |= set(snapshot.macro_slots([matrix]))
    if not isinstance(record, Mapping):
        raise ValueError("record must be an object")
    imported = deepcopy(record)
    actions = imported.get("value")
    if not isinstance(actions, list):
        raise ValueError("record value must be an action list")
    available = [slot for slot in range(50) if slot not in reserved]
    allocations: list[tuple[int, int, int | None]] = []
    macros: dict[str, str] = {}
    for action_index, action in enumerate(actions):
        if not isinstance(action, Mapping):
            raise ValueError(f"action {action_index} must be an object")
        if action.get("type") != "ConfigMacro":
            if encode(action)[0] == 9:
                raise ValueError("import contains raw macro binding without embedded payload")
            continue
        if not available:
            raise ValueError("no macro slots available for import")
        converted = convert(action)
        slot = available.pop(0)
        source_slot = action.get("macroIndex") if type(action.get("macroIndex")) is int else None
        action["macroIndex"] = slot
        allocations.append((action_index, slot, source_slot))
        macros[str(slot)] = converted["payload"]
    result = preview(imported, target, include_macros=True)
    if result["unresolved_macro_slots"]:
        raise ValueError("import contains raw macro bindings without embedded payloads")
    return {
        "format": "epomaker-glyph-import-plan",
        "schema_version": 1,
        "target": target,
        "profile": profile,
        "matrix": result["matrix"],
        "macros": macros,
        "assignments": [
            {"action_index": index, "source_slot": source, "slot": slot}
            for index, slot, source in allocations
        ],
        "reserved_slots": sorted(reserved),
        "write_ready": False,
    }
