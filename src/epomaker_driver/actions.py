"""Semantic four-byte bindings, preserving unknown actions during decoding."""

from .codec import bounded

KEYS = {
    **{chr(97 + i): 4 + i for i in range(26)},
    **{str(i): 29 + i for i in range(1, 10)},
    "0": 39,
    **dict(
        zip(
            (
                "enter",
                "escape",
                "backspace",
                "tab",
                "space",
                "minus",
                "equal",
                "left-bracket",
                "right-bracket",
                "backslash",
            ),
            range(40, 50),
            strict=True,
        )
    ),
    "semicolon": 51,
    "quote": 52,
    "grave": 53,
    "comma": 54,
    "period": 55,
    "slash": 56,
    "caps-lock": 57,
    **{f"f{i}": 57 + i for i in range(1, 13)},
    "print-screen": 70,
    "scroll-lock": 71,
    "pause": 72,
    "insert": 73,
    "home": 74,
    "page-up": 75,
    "delete": 76,
    "end": 77,
    "page-down": 78,
    "right": 79,
    "left": 80,
    "down": 81,
    "up": 82,
    **dict(
        zip(
            (
                "left-ctrl",
                "left-shift",
                "left-alt",
                "left-meta",
                "right-ctrl",
                "right-shift",
                "right-alt",
                "right-meta",
            ),
            range(224, 232),
            strict=True,
        )
    ),
}
MODIFIERS = dict(
    zip(
        ("ctrl", "shift", "alt", "meta", "right-ctrl", "right-shift", "right-alt", "right-meta"),
        (1 << i for i in range(8)),
        strict=True,
    )
)
MEDIA = {
    "next": 181,
    "previous": 182,
    "stop": 183,
    "play-pause": 205,
    "mute": 226,
    "volume-up": 233,
    "volume-down": 234,
}
MOUSE = {
    "left": 240,
    "right": 241,
    "middle": 242,
    "back": 243,
    "forward": 244,
    "wheel-left": 245,
    "wheel-right": 246,
    "wheel-up": 247,
    "wheel-down": 248,
}
MACRO_MODES = {"count": 0, "toggle": 1, "held": 2}


def key_usage(value):
    if isinstance(value, str):
        if value.lower() not in KEYS:
            raise ValueError(f"unknown key: {value}")
        return KEYS[value.lower()]
    return bounded(value, 255, "key usage")


def keyboard(key, *, second=0, modifiers=()):
    mask = 0
    for modifier in modifiers:
        if modifier not in MODIFIERS:
            raise ValueError(f"unknown modifier: {modifier}")
        mask |= MODIFIERS[modifier]
    return bytes([0, mask, key_usage(key), key_usage(second)])


def media(name):
    if name not in MEDIA:
        raise ValueError("unknown media action")
    return bytes([3, 0]) + MEDIA[name].to_bytes(2, "little")


def mouse(name):
    if name not in MOUSE:
        raise ValueError("unknown mouse action")
    return bytes([1, 0, MOUSE[name], 0])


def macro(slot, mode="count"):
    if mode not in MACRO_MODES:
        raise ValueError("unknown macro playback mode")
    return bytes([9, MACRO_MODES[mode], bounded(slot, 255, "macro slot"), 0])


def decode(data):
    data = bytes(data)
    if len(data) != 4:
        raise ValueError("action must be four bytes")
    raw = data.hex()
    if data in (bytes(4), bytes([0, 0, 3, 0])):
        return {"type": "disabled", "raw": raw}
    if data == bytes([0, 0, 1, 0]):
        return {"type": "unknown", "raw": raw}
    if data[0] == 0:
        return {
            "type": "keyboard",
            "key": data[2],
            "second": data[3],
            "modifiers": [name for name, mask in MODIFIERS.items() if data[1] & mask],
            "raw": raw,
        }
    if data[0] == 9 and data[1] in MACRO_MODES.values() and data[3] == 0:
        return {
            "type": "macro",
            "slot": data[2],
            "mode": next(k for k, v in MACRO_MODES.items() if v == data[1]),
            "raw": raw,
        }
    for kind, mapping in (("media", MEDIA), ("mouse", MOUSE)):
        opcode = 3 if kind == "media" else 1
        if data[0] == opcode and data[1] == 0:
            code = int.from_bytes(data[2:4], "little")
            if code in mapping.values():
                return {
                    "type": kind,
                    "name": next(k for k, v in mapping.items() if v == code),
                    "raw": raw,
                }
    return {"type": "unknown", "raw": raw}
