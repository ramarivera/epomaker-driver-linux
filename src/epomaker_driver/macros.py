"""Editable macro events, including explicit-delay motion. See docs/macros.md."""

import struct

from . import codec
from .errors import ProtocolError

BUTTONS = {"left": 240, "right": 241, "middle": 242, "back": 243, "forward": 244}


def encode(repeat, events):
    codec.bounded(repeat, 65535, "repeat")
    if not isinstance(events, list):
        raise ValueError("events must be a list")
    result = bytearray(struct.pack("<H", repeat))
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("each event must be an object")
        event = dict(event)
        kind = event.pop("type", "keyboard")
        if kind == "keyboard":
            if set(event) != {"hid_usage", "down", "delay_ms"}:
                raise ValueError("keyboard event needs hid_usage, down and delay_ms")
            data = codec.macro_keyboard_event(**event)
        elif kind == "mouse_button":
            if (
                set(event) != {"button", "down", "delay_ms"}
                or not isinstance(event["button"], str)
                or event["button"] not in BUTTONS
            ):
                raise ValueError("mouse_button event needs a known button, down and delay_ms")
            tail = codec.macro_keyboard_event(4, event["down"], event["delay_ms"])[1:]
            data = bytes([BUTTONS[event["button"]]]) + tail
        elif kind == "mouse_move":
            if set(event) != {"dx", "dy", "delay_ms"}:
                raise ValueError("mouse_move event needs dx, dy and delay_ms")
            for axis in ("dx", "dy"):
                if type(event[axis]) is not int or not -128 <= event[axis] <= 127:
                    raise ValueError("mouse movement must be signed 8-bit integers")
            delay = codec.bounded(event["delay_ms"], 65535, "delay_ms")
            if delay == 0:
                raise ValueError("delay_ms must be positive")
            # The long form is unambiguous even for delays less than 128 ms.
            data = bytes([249, 0]) + struct.pack("<bbH", event["dx"], event["dy"], delay)
        else:
            raise ValueError(f"unknown macro event type: {kind}")
        result.extend(data)
        if len(result) > 256:
            raise ValueError("macro exceeds 256-byte storage")
    return bytes(result).ljust(256, b"\0")


def decode(data):
    data = bytes(data)
    if len(data) != 256:
        raise ProtocolError("macro data must be exactly 256 bytes")
    events = []
    offset = 2
    while offset < len(data) and any(data[offset:]):
        if offset + 2 > len(data):
            raise ProtocolError("truncated macro event")
        code, marker = data[offset : offset + 2]
        offset += 2
        if code == 249:
            if marker != 0:
                raise ProtocolError(
                    "compact mouse-motion delay is ambiguous; retain raw macro data"
                )
            if offset + 4 > len(data):
                raise ProtocolError("truncated mouse-motion event")
            dx, dy, delay = struct.unpack_from("<bbH", data, offset)
            offset += 4
            event = {"type": "mouse_move", "dx": dx, "dy": dy}
        else:
            if 4 <= code <= 239:
                event = {"hid_usage": code, "down": bool(marker & 128)}
            elif code in BUTTONS.values():
                event = {
                    "type": "mouse_button",
                    "button": next(k for k, v in BUTTONS.items() if v == code),
                    "down": bool(marker & 128),
                }
            else:
                raise ProtocolError(f"unsupported macro event 0x{code:02x}; retain raw data")
            delay = marker & 127
            if delay == 0:
                if offset + 2 > len(data):
                    raise ProtocolError("truncated macro delay")
                delay = struct.unpack_from("<H", data, offset)[0]
                offset += 2
        if delay == 0:
            raise ProtocolError("zero-delay macro event is ambiguous; retain raw data")
        events.append({**event, "delay_ms": delay})
    return {"repeat": struct.unpack_from("<H", data)[0], "events": events}
