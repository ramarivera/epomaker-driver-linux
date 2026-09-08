"""Semantic CH585 mouse bindings.

The CH585 stores button assignments as four-byte values.  This module keeps
the mouse-specific values separate from the shared keyboard action codec while
delegating common keyboard, media, and macro values to :mod:`actions`.
"""

from . import actions

# Functional CH585 action values.  This is the named subset needed by the
# mouse controls; the vendor protocol has additional gamepad and macro forms.
BINDINGS = {
    "left": bytes.fromhex("0100f000"),
    "right": bytes.fromhex("0100f100"),
    "middle": bytes.fromhex("0100f200"),
    "back": bytes.fromhex("0100f300"),
    "forward": bytes.fromhex("0100f400"),
    "wheel-left": bytes.fromhex("0100f500"),
    "wheel-right": bytes.fromhex("0100f600"),
    "wheel-up": bytes.fromhex("0100f700"),
    "wheel-down": bytes.fromhex("0100f800"),
    "scroll-up": bytes.fromhex("0100f501"),
    "scroll-down": bytes.fromhex("0100f5ff"),
    "move-left": bytes.fromhex("0100f6fb"),
    "move-right": bytes.fromhex("0100f605"),
    "move-up": bytes.fromhex("0100f7fb"),
    "move-down": bytes.fromhex("0100f705"),
    "dpi-cycle": bytes.fromhex("14000000"),
    "dpi-up": bytes.fromhex("14000100"),
    "dpi-down": bytes.fromhex("00020014"),
    "profile-cycle": bytes.fromhex("08000300"),
    "pairing": bytes.fromhex("0a050000"),
    "lighting-cycle": bytes.fromhex("0d010000"),
}


def mouse(name):
    """Return the four-byte CH585 binding named by *name*."""

    try:
        return BINDINGS[name]
    except (KeyError, TypeError) as error:
        raise ValueError(f"unknown mouse action: {name}") from error


def decode(data):
    """Decode a four-byte action, preferring semantic CH585 mouse names."""

    try:
        data = bytes(memoryview(data))
    except (TypeError, ValueError) as error:
        raise ValueError("action must be four bytes") from error
    if len(data) != 4:
        raise ValueError("action must be four bytes")
    raw = data.hex()
    for name, binding in BINDINGS.items():
        if data == binding:
            return {"type": "mouse", "name": name, "raw": raw}
    # These values are ambiguous in the shared keyboard codec.  CH585 uses
    # keycodes 1 and 3 as reserved slots, so retain them as unknown packets.
    if data[0] == 0 and data[1] == 0 and data[3] == 0 and data[2] in (1, 3):
        return {"type": "unknown", "raw": raw}
    return actions.decode(data)
