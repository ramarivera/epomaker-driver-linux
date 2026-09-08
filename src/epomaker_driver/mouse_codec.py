"""Pure codec for the CommonMSCH585 mouse reports."""

from __future__ import annotations

from .codec import packet

_RATES = {125: 8, 250: 4, 500: 2, 1000: 1, 2000: 132, 4000: 130, 8000: 129}
_RATE_CODES = {code: rate for rate, code in _RATES.items()}

# Scalar wire evidence: docs/ch585-protocol.md; Mac 5d75ced3.js / Win 78e397ff.js.
# Model and firmware gates belong in the backend.
SETTINGS = {
    "debounce": (0x84, 0x04, 1, 10, "uint8"),
    "scroll_up_time": (0x85, 0x05, 1, 255, "uint8"),
    "sleep_24": (0x86, 0x06, 2, 0xFFFF, "uint16"),
    "sleep_bt": (0x87, 0x07, 2, 0xFFFF, "uint16"),
    "lod": (0x91, 0x11, 1, 2, "uint8"),
    "line_repair": (0x92, 0x12, 1, 1, "bool"),
    "wave_repair": (0x93, 0x13, 1, 1, "bool"),
    "low_latency": (0x8C, 0x0C, 1, 1, "uint8"),
}


def _raw64(raw, name):
    if isinstance(raw, int):
        raise ValueError(f"{name} must be 64 bytes")
    try:
        value = bytes(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be 64 bytes") from error
    if len(value) != 64:
        raise ValueError(f"{name} must be 64 bytes")
    return value


def _uint(value, maximum, name):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"{name} must be an integer in 0..{maximum}")
    return value


def _setting(name):
    try:
        return SETTINGS[name]
    except KeyError as error:
        raise ValueError(f"unknown mouse setting: {name}") from error


def setting_query(name):
    """Return the 64-byte query packet for a named scalar setting."""

    get_opcode, _set_opcode, _width, _maximum, _kind = _setting(name)
    return packet([get_opcode])


def setting_command(name, value):
    """Encode one scalar setting write, with no model-specific coercion."""

    _get_opcode, set_opcode, width, maximum, kind = _setting(name)
    if kind == "bool":
        if type(value) is not bool:
            raise ValueError(f"{name} must be a boolean")
        numeric = int(value)
    else:
        numeric = _uint(value, maximum, name)
        if name == "debounce" and numeric < 1:
            raise ValueError("debounce must be in 1..10")
        if name == "scroll_up_time" and numeric < 1:
            raise ValueError("scroll_up_time must be in 1..255")
    payload = [set_opcode, numeric]
    if width == 2:
        payload = [set_opcode, numeric & 0xFF, numeric >> 8]
    return packet(payload)


def parse_setting(name, raw):
    """Decode one 64-byte scalar response without normalizing unknown flags."""

    get_opcode, _set_opcode, width, _maximum, kind = _setting(name)
    value = _raw64(raw, f"{name} response")
    if value[0] != get_opcode:
        raise ValueError(f"expected a 0x{get_opcode:02x} {name} response")
    if width == 2:
        numeric = int.from_bytes(value[1:3], "little")
    else:
        numeric = value[1]
    if kind == "bool":
        if numeric not in (0, 1):
            raise ValueError(f"{name} response has an invalid boolean value")
        return bool(numeric)
    # Reads preserve the device's raw byte, even if it is outside the UI's
    # write range; this permits a bounded repair write by the backend.
    return numeric


def identity(raw):
    value = _raw64(raw, "identity response")
    if value[0] != 0x8F:
        raise ValueError("expected a 0x8f identity response")
    version = int.from_bytes(value[5:7], "little") or None
    return {
        "device_id": int.from_bytes(value[1:5], "little"),
        "usb_version": version,
        "is_boot": None,
        "raw": list(value),
    }


def dpi(raw):
    value = _raw64(raw, "DPI response")
    if value[0] != 0x90:
        raise ValueError("expected a 0x90 DPI response")
    levels = []
    for slot in range(8):
        levels.append(
            {
                "x": int.from_bytes(value[8 + slot * 2 : 10 + slot * 2], "little"),
                "y": int.from_bytes(value[24 + slot * 2 : 26 + slot * 2], "little"),
                "rgb": int.from_bytes(value[40 + slot * 3 : 43 + slot * 3], "big"),
            }
        )
    return {
        "profile": value[1],
        "current": value[2],
        "count": value[3],
        "levels": levels,
        "raw": list(value),
    }


def dpi_command(
    raw,
    *,
    profile,
    current=None,
    slot=None,
    x=None,
    y=None,
    rgb=None,
    count=None,
):
    value = bytearray(_raw64(raw, "DPI response"))
    if value[0] != 0x90:
        raise ValueError("expected a 0x90 DPI response")
    _uint(profile, 7, "profile")
    value[1] = profile
    if current is not None:
        _uint(current, 7, "current")
        value[2] = current
    if count is not None:
        _uint(count, 8, "count")
        if count == 0:
            raise ValueError("count must be at least 1")
        value[3] = count
    fields = (x, y, rgb)
    if any(item is not None for item in fields):
        if slot is None:
            raise ValueError("slot is required for a DPI level patch")
        _uint(slot, 7, "slot")
        if x is not None:
            _uint(x, 0xFFFF, "x")
            value[8 + slot * 2 : 10 + slot * 2] = x.to_bytes(2, "little")
        if y is not None:
            _uint(y, 0xFFFF, "y")
            value[24 + slot * 2 : 26 + slot * 2] = y.to_bytes(2, "little")
        if rgb is not None:
            _uint(rgb, 0xFFFFFF, "rgb")
            value[40 + slot * 3 : 43 + slot * 3] = rgb.to_bytes(3, "big")
    elif slot is not None:
        raise ValueError("a DPI level patch is required when slot is supplied")
    if current is None and count is None and not any(item is not None for item in fields):
        raise ValueError("DPI command has no changes")
    value[0] = 0x10
    # The vendor setter starts with a zeroed header, not response status bits.
    value[4:7] = bytes(3)
    return packet(value)


def profile_command(index):
    return packet([0x02, _uint(index, 7, "profile")])


def rate_command(hz):
    if type(hz) is not int or hz not in _RATES:
        raise ValueError("unsupported report rate")
    return packet([0x08, _RATES[hz]])


def parse_rate(raw):
    value = _raw64(raw, "report-rate response")
    if value[0] != 0x88:
        raise ValueError("expected a 0x88 report-rate response")
    return _RATE_CODES.get(value[1])


def aggregate(raw):
    value = _raw64(raw, "aggregate response")
    if value[0] != 0x9F:
        raise ValueError("expected a 0x9f aggregate response")
    return {
        "profile": value[8],
        "debounce": value[9],
        "scroll_up_time": value[10],
        "sleep_24g": int.from_bytes(value[11:13], "little"),
        "sleep_bluetooth": int.from_bytes(value[13:15], "little"),
        "report_rate": _RATE_CODES.get(value[15]),
        "silent_height": value[16],
        "line_repair": value[17] == 1,
        "wave_repair": value[18] == 1,
        "motion_sync": value[19] == 1,
        "report_rates": [_RATE_CODES.get(code) for code in value[20:28]],
        "fps_20000": value[28] == 1,
        "low_latency": value[40],
        "raw": list(value),
    }
