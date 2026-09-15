"""Serialize vendor profile actions to four byte values.

This is a shared vendor serializer for opaque profile interchange. Its action
vocabulary is broader than the Glyph feature surface; callers still need to
apply the appropriate model capability gate before exposing an action.
"""

from __future__ import annotations

from collections.abc import Mapping

from .models import data_file


def _strict_int(value, field: str, *, minimum: int = 0, maximum: int = 255) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return value


def _bytes4(value, field: str = "value") -> bytes:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError(f"{field} must contain exactly four bytes")
    return bytes(_strict_int(item, f"{field}[{index}]") for index, item in enumerate(value))


def _tables() -> Mapping:
    tables = data_file("vendor-action-tables.json")
    if not isinstance(tables, dict):
        raise ValueError("vendor action tables must be an object")
    for name in ("functions", "mouse", "gamepad"):
        if not isinstance(tables.get(name), dict):
            raise ValueError(f"vendor action table missing {name}")
    return tables


def _lookup(table: Mapping, key, field: str) -> bytes:
    if key not in table:
        raise ValueError(f"unknown {field}: {key!r}")
    return _bytes4(table[key], f"{field} entry")


def encode(action: Mapping) -> bytes:
    """Return the vendor's four byte representation of *action*.

    Unrelated metadata is deliberately ignored, allowing opaque actions to
    retain fields needed by higher-level interchange code.
    """
    if not isinstance(action, Mapping):
        raise ValueError("action must be an object")
    kind = action.get("type")
    if kind == "forbidden":
        return b"\0\0\0\0"
    if kind == "combo":
        key = _strict_int(action.get("key"), "key", maximum=0xFFFFFFFF)
        if key <= 0xFF:
            return bytes(
                (
                    0,
                    _strict_int(action.get("skey"), "skey"),
                    key,
                    _strict_int(action.get("key2"), "key2"),
                )
            )
        return key.to_bytes(4, "big")
    if kind == "ConfigUnknown":
        return _bytes4(action.get("value"))
    if kind == "ConfigFunction":
        if "value" in action:
            return _bytes4(action["value"])
        key = action.get("key")
        if not isinstance(key, str):
            raise ValueError("ConfigFunction key must be a string when value is absent")
        return _lookup(_tables()["functions"], key, "function")
    if kind == "ConfigMouse":
        key = action.get("key")
        if isinstance(key, bool) or not isinstance(key, int):
            raise ValueError("mouse key must be an integer")
        return _lookup(_tables()["mouse"], str(key), "mouse key")
    if kind == "ConfigGamepad":
        key = action.get("key")
        if not isinstance(key, str):
            raise ValueError("gamepad key must be a string")
        return _lookup(_tables()["gamepad"], key, "gamepad key")
    if kind in ("ConfigSnap", "ConfigMDS"):
        opcode = 22 if kind == "ConfigSnap" else 23
        return bytes(
            (
                opcode,
                _strict_int(action.get("number"), "number"),
                _strict_int(action.get("keyCode"), "keyCode"),
                0,
            )
        )
    if kind == "ConfigMT":
        time = _strict_int(action.get("time"), "time", maximum=2550)
        if time % 10:
            raise ValueError("time must be a multiple of 10")
        return bytes(
            (
                24,
                _strict_int(action.get("keyCode"), "keyCode"),
                _strict_int(action.get("keyCode2"), "keyCode2"),
                time // 10,
            )
        )
    if kind == "ConfigMacro":
        modes = {"repeat_times": 0, "on_off": 1, "touch_repeat": 2}
        macro_type = action.get("macroType")
        if not isinstance(macro_type, str):
            raise ValueError("macroType must be a string")
        if macro_type not in modes:
            raise ValueError(f"unknown macroType: {macro_type!r}")
        return bytes((9, modes[macro_type], _strict_int(action.get("macroIndex"), "macroIndex"), 0))
    if kind == "ConfigControlRecoil":
        methods = {"normal": 4, "switch_keep": 6, "switch_toggle": 7}
        method = action.get("method")
        if not isinstance(method, str):
            raise ValueError("recoil method must be a string")
        if method not in methods:
            raise ValueError(f"unknown recoil method: {method!r}")
        return bytes((22, methods[method], _strict_int(action.get("gunIndex"), "gunIndex"), 0))
    raise ValueError(f"unknown action type: {kind!r}")
