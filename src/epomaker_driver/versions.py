"""Modern keyboard version queries; see docs/he60-lite-research.md.

Pure commands and parsers only. Model capability checks remain the caller's
responsibility; these offsets must not be used for the older YC3121 backend.
"""

from .codec import packet

_COMPONENTS = {"usb": (0x8F, 7), "rf": (0x80, 1), "mled": (0xAE, 1), "oled": (0xAD, 1)}


def _component(component):
    if component not in _COMPONENTS:
        raise ValueError("version component must be usb, rf, mled or oled")
    return _COMPONENTS[component]


def version_request(component):
    opcode, _ = _component(component)
    return packet([opcode])


def parse_version(component, response):
    """Decode uint16 little-endian versions, preserving zero as unavailable.

    OLED replies contain both display-controller and flash versions. No
    interpretation as semantic-version strings or bootloader status is made.
    """
    opcode, offset = _component(component)
    raw = bytes(response)
    required = 5 if component == "oled" else offset + 2
    if len(raw) < required or len(raw) > 64 or raw[0] != opcode:
        raise ValueError(f"invalid {component} version response")
    value = int.from_bytes(raw[offset : offset + 2], "little") or None
    if component == "oled":
        return {"oled": value, "flash": int.from_bytes(raw[3:5], "little") or None}
    return value
