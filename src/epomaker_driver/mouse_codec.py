"""Pure codec for the CommonMSCH585 mouse reports."""

from __future__ import annotations

from .codec import packet

_RATES = {125: 8, 250: 4, 500: 2, 1000: 1, 2000: 132, 4000: 130, 8000: 129}
_RATE_CODES = {code: rate for rate, code in _RATES.items()}


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
