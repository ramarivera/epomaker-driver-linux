"""Export a Glyph snapshot bank to the vendor profile action format."""

from __future__ import annotations

from collections.abc import Mapping

from . import macros, snapshot
from .models import data_file, glyph_matrix
from .vendor_config import TARGETS, _identities


def _event_pairs(decoded: Mapping) -> list[dict]:
    result: list[dict] = []
    for event in decoded["events"]:
        delay = event.pop("delay_ms")
        kind = event.pop("type", "keyboard")
        if kind == "keyboard":
            result.append(
                {
                    "type": "keyboard",
                    "value": event.pop("hid_usage"),
                    "action": "down" if event.pop("down") else "up",
                }
            )
        elif kind == "mouse_button":
            button = event.pop("button")
            code = macros.BUTTONS[button]
            table = data_file("vendor-action-tables.json").get("mouse", {})
            values = [int(key) for key, raw in table.items() if len(raw) == 4 and raw[2] == code]
            if not values:
                raise ValueError(f"no vendor mouse enum for button {button}")
            result.append(
                {
                    "type": "mouse_button",
                    "value": min(values),
                    "action": "down" if event.pop("down") else "up",
                }
            )
        elif kind == "mouse_move":
            result.append({"type": "mouse_move", "dx": event.pop("dx"), "dy": event.pop("dy")})
        else:
            raise ValueError(f"unsupported macro event type: {kind}")
        result.append({"type": "delay", "value": delay})
    return result


def export_record(
    current_snapshot: Mapping,
    target: str = "Main",
    profile: int = 0,
    name: str = "Glyph configuration",
) -> dict:
    """Export one snapshot bank without changing the source snapshot."""
    if target not in TARGETS:
        raise ValueError("target must be Main, Fn Windows, or Fn Mac")
    if type(profile) is not int or not 0 <= profile <= 2:
        raise ValueError("profile must be an integer from 0 to 2")
    if target != "Main" and profile != 0:
        raise ValueError("Fn export requires profile 0")
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise ValueError("name must be nonempty and at most 100 characters")
    matrices, fn_matrices, macro_data, _settings, _sleep, _pictures = snapshot.validate(
        current_snapshot
    )
    if current_snapshot["identity"]["device_id"] != 3059 or len(matrices) != 3:
        raise ValueError("snapshot must contain three Glyph profiles")
    selected = (
        matrices[profile]
        if target == "Main"
        else fn_matrices["win" if target == "Fn Windows" else "mac"]
    )
    baseline = glyph_matrix()
    identities = _identities(baseline)
    actions = []
    for slot in range(128):
        current = selected[slot * 4 : slot * 4 + 4]
        if current == baseline[slot * 4 : slot * 4 + 4]:
            continue
        identity = next((key for key, slots in identities.items() if slot in slots), None)
        if identity is None:
            raise ValueError(f"changed slot {slot} has no resolvable vendor identity")
        index = identities[identity].index(slot)
        action = {"original": identity, "index": index}
        if current[0] == 9:
            if current[3] != 0 or current[1] not in (0, 1, 2):
                raise ValueError(f"invalid macro binding at slot {slot}")
            macro_slot = current[2]
            if macro_slot not in macro_data:
                raise ValueError(f"snapshot omits macro payload {macro_slot}")
            modes = ("repeat_times", "on_off", "touch_repeat")
            decoded = macros.decode(macro_data[macro_slot])
            action.update(
                type="ConfigMacro",
                macroType=modes[current[1]],
                macroIndex=macro_slot,
                repeatCount=decoded["repeat"],
                macro=_event_pairs(decoded),
            )
        else:
            action.update(type="ConfigUnknown", value=list(current))
        actions.append(action)
    return {
        "name": name.strip(),
        "deviceType": {"id": 3059, "name": "Glyph", "displayName": "Glyph"},
        "fn": target != "Main",
        "value": actions,
    }
