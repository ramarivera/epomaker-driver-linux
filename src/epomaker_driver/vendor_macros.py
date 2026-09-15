"""Convert vendor macro payloads into the driver's validated macro format."""

from __future__ import annotations

from collections.abc import Mapping

from . import macros
from .models import data_file


def _integer(value, field: str, maximum: int) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"{field} must be an integer between 0 and {maximum}")
    return value


def _delay(event: Mapping) -> int:
    if not {"type", "value"}.issubset(event) or event.get("type") != "delay":
        raise ValueError("macro events must alternate payload events and delays")
    delay = _integer(event.get("value"), "delay", 65535)
    if delay == 0:
        raise ValueError("delay must be positive")
    return delay


def _mouse_button(value) -> str:
    if type(value) is not int:
        raise ValueError("mouse button value must be an integer")
    table = data_file("vendor-action-tables.json").get("mouse", {})
    raw = table.get(str(value))
    if isinstance(raw, list) and len(raw) == 4:
        for button, code in macros.BUTTONS.items():
            if raw[2] == code:
                return button
    raise ValueError(f"unknown vendor mouse button: {value!r}")


def convert(action: Mapping) -> dict:
    """Convert one vendor ``ConfigMacro`` action, including its 256-byte payload."""
    if not isinstance(action, Mapping) or action.get("type") != "ConfigMacro":
        raise ValueError("action must be a ConfigMacro object")
    if "macro" not in action or not isinstance(action["macro"], list):
        raise ValueError("ConfigMacro macro must be an explicit list")
    repeat = _integer(action.get("repeatCount"), "repeatCount", 65535)
    source = action["macro"]
    events = []
    if len(source) % 2:
        raise ValueError("macro must end with a delay event")
    for offset in range(0, len(source), 2):
        event, delay_event = source[offset : offset + 2]
        if not isinstance(event, Mapping) or not isinstance(delay_event, Mapping):
            raise ValueError("macro events must be objects")
        delay = _delay(delay_event)
        kind = event.get("type")
        if kind == "keyboard":
            if not {"type", "value", "action"}.issubset(event):
                raise ValueError("keyboard event needs type, value, and action")
            usage = _integer(event.get("value"), "keyboard value", 255)
            if event.get("action") not in ("down", "up"):
                raise ValueError("keyboard action must be down or up")
            events.append(
                {"hid_usage": usage, "down": event["action"] == "down", "delay_ms": delay}
            )
        elif kind == "mouse_button":
            if not {"type", "value", "action"}.issubset(event):
                raise ValueError("mouse button event needs type, value, and action")
            if event.get("action") not in ("down", "up"):
                raise ValueError("mouse button action must be down or up")
            events.append(
                {
                    "type": "mouse_button",
                    "button": _mouse_button(event.get("value")),
                    "down": event["action"] == "down",
                    "delay_ms": delay,
                }
            )
        elif kind == "mouse_move":
            if not {"type", "dx", "dy"}.issubset(event):
                raise ValueError("mouse move event needs type, dx, and dy")
            events.append(
                {
                    "type": "mouse_move",
                    "dx": _signed(event.get("dx"), "dx"),
                    "dy": _signed(event.get("dy"), "dy"),
                    "delay_ms": delay,
                }
            )
        else:
            raise ValueError(f"unknown macro event type: {kind!r}")
    payload = macros.encode(repeat, events)
    return {"repeat": repeat, "events": events, "payload": payload.hex()}


def _signed(value, field: str) -> int:
    if type(value) is not int or not -128 <= value <= 127:
        raise ValueError(f"{field} must be a signed 8-bit integer")
    return value
