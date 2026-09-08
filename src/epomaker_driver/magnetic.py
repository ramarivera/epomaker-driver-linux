"""Pure magnetic-key packet codec for the modern YC3123 protocol."""

from __future__ import annotations

import math
from decimal import Decimal

from .codec import packet

MULTI_GET = 0xE5
MULTI_SET = 0x65
TRAVEL_FIELDS = frozenset((0, 1, 2, 3, 4, 6, 251))
BYTE_FIELDS = frozenset((7, 9, 252))
KNOWN_FIELDS = TRAVEL_FIELDS | BYTE_FIELDS | frozenset((5, 8, 10))
READ_PAGES = {0: 4, 1: 4, 2: 4, 3: 4, 4: 4, 5: 2, 6: 4, 7: 2, 9: 2, 10: 8, 251: 2, 252: 2}
WRITE_WIDTHS = {
    field: 1 if field in (5, 7, 9, 251, 252) else 4 if field == 8 else 2
    for field in KNOWN_FIELDS - {10}
}


def _multiplier(value):
    if type(value) is not int or value not in (10, 100, 200):
        raise ValueError("multiplier must be 10, 100 or 200")


def _key_index(value):
    if type(value) is not int or not 0 <= value <= 127:
        raise ValueError("key index must be 0..127")


def _payload(value):
    if isinstance(value, (int, str)):
        raise ValueError("payload must be a byte sequence")
    return bytes(value)


def travel_multiplier(*, usb=None, rf=None):
    for name, v in (("usb", usb), ("rf", rf)):
        if v is not None and (
            isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 0xFFFF
        ):
            raise ValueError(f"{name} version must be a uint16")
    v = rf or usb
    return 10 if v is None or v < 0x300 else 100 if v < 0x500 else 200


def top_dead_zone_supported(*, usb=None, rf=None):
    for name, value in (("usb", usb), ("rf", rf)):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFF
        ):
            raise ValueError(f"{name} version must be a uint16")
    return (rf is not None and rf >= 0x400) or (usb is not None and usb >= 0x400)


def encode_read(field, page):
    _field(field)
    if (
        field not in READ_PAGES
        or not isinstance(page, int)
        or isinstance(page, bool)
        or not 0 <= page < READ_PAGES[field]
    ):
        raise ValueError("page is out of range for field")
    return packet([MULTI_GET, field, 1, page])


def encode_write(field, key_index, values, *, commit):
    _field(field)
    if field == 10:
        raise ValueError("field 10 is read-only")
    _key_index(key_index)
    if type(commit) is not bool:
        raise ValueError("commit must be boolean")
    payload = _payload(values)
    if len(payload) != WRITE_WIDTHS[field]:
        raise ValueError("invalid payload width for magnetic field")
    return packet([MULTI_SET, field, 0, key_index, int(commit), 0, 0, 0] + list(payload))


def decode_page(response):
    if len(response) != 64:
        raise ValueError("magnetic response must be exactly 64 bytes")
    return bytes(response)


def assemble_pages(pages, *, length):
    """Join complete 64-byte responses and retain exactly the requested bytes."""
    raw = b"".join(decode_page(page) for page in pages)
    if type(length) is not int or not 0 <= length <= len(raw):
        raise ValueError("assembled magnetic length is out of range")
    return raw[:length]


def key_field(data, slot, *, field, stage=0):
    """Read one slot from an assembled field; field 10 has four 128-byte stages."""
    _field(field)
    _key_index(slot)
    if field not in READ_PAGES:
        raise ValueError("field is not a bulk read field")
    if len(data) != READ_PAGES[field] * 64:
        raise ValueError("assembled field is incomplete or oversized")
    if type(stage) is not int or not 0 <= stage < (4 if field == 10 else 1):
        raise ValueError("stage must be 0..3 for field 10 and zero otherwise")
    if field == 10:
        offset = stage * 128 + slot
        return data[offset]
    width = 1 if field in BYTE_FIELDS or field in (5, 251) else 2
    offset = slot * width
    return bytes(data[offset : offset + width])


def encode_field(field, value, *, multiplier):
    # Preserve decimal UI increments; binary multiplication can lose one unit.
    # Fractional wire units still truncate; see docs/ry5088-wireless.md.
    _field(field)
    _multiplier(multiplier)
    if field == 10:
        raise ValueError("field 10 is read-only")
    if field == 251:
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError("top dead zone must be one byte")
        raw = int(Decimal(str(value)) * multiplier)
        if raw > 255:
            raise ValueError("top dead zone exceeds one-byte encoding")
        return bytes((raw,))
    if field in BYTE_FIELDS:
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 255:
            raise ValueError("byte magnetic field must be 0..255")
        return bytes((value,))
    if field == 8:
        if isinstance(value, int):
            raise ValueError("trigger modes require four bytes")
        raw = _payload(value)
        if len(raw) != 4:
            raise ValueError("trigger modes require four bytes")
        return raw
    if field == 5:
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            or value % 10
            or value // 10 > 255
        ):
            raise ValueError("MT time must be a nonnegative multiple of 10 ms")
        return bytes((value // 10,))
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError("magnetic travel must be finite and nonnegative")
    raw = int(Decimal(str(value)) * multiplier)
    if raw > 0xFFFF:
        raise ValueError("magnetic travel exceeds two-byte encoding")
    return raw.to_bytes(2, "little")


def decode_field(field, payload, *, multiplier):
    _field(field)
    _multiplier(multiplier)
    payload = _payload(payload)
    if field == 251:
        if len(payload) != 1:
            raise ValueError("top dead zone requires one byte")
        return payload[0] / multiplier
    if field in BYTE_FIELDS:
        if len(payload) != 1:
            raise ValueError("byte magnetic field requires one byte")
        return payload[0]
    if field == 10:
        raise ValueError("field 10 is read-only")
    if field == 8:
        if len(payload) != 4:
            raise ValueError("trigger modes require four bytes")
        return bytes(payload)
    if field == 5:
        if len(payload) != 1:
            raise ValueError("MT time payload must be one byte")
        return payload[0] * 10
    if len(payload) != 2:
        raise ValueError("travel field requires two bytes and a valid multiplier")
    return int.from_bytes(payload, "little") / multiplier


def field_write_order(*, changed, mode_changed, top_supported):
    if type(mode_changed) is not bool or type(top_supported) is not bool:
        raise ValueError("mode_changed and top_supported must be boolean")
    for field in changed:
        _field(field)
    allowed = TRAVEL_FIELDS | {5, 7, 8}
    if not changed <= allowed:
        raise ValueError("unknown magnetic field")
    if 251 in changed and not top_supported:
        raise ValueError("top dead zone is unavailable for this firmware")
    order = ([7] if mode_changed else []) + [
        f for f in (0, 1, 6, 2, 3, 4, 8, 5, 251) if f in changed
    ]
    if mode_changed and 7 not in changed:
        raise ValueError("mode change requires field 7")
    if not mode_changed and 7 in changed:
        raise ValueError("field 7 requires mode_changed")
    return order


def write_commands(fields, *, key_index, multiplier, mode_changed=False, top_supported=False):
    """Plan a single key's already-selected changes; no writes or cached diffing.

    Caller selects changed fields and enforces model limits and RT-mode rules.
    Snap pairing and axis changes use separate vendor transactions and are not
    accepted here. The final command commits the entire simple-field group.
    """
    _key_index(key_index)
    _multiplier(multiplier)
    order = field_write_order(
        changed=set(fields), mode_changed=mode_changed, top_supported=top_supported
    )
    return [
        encode_write(
            field,
            key_index,
            encode_field(field, fields[field], multiplier=multiplier),
            commit=index == len(order) - 1,
        )
        for index, field in enumerate(order)
    ]


def _field(field):
    _byte(field, "field")
    if field not in KNOWN_FIELDS:
        raise ValueError("unknown magnetic field")


def _byte(value, name):
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 255:
        raise ValueError(f"{name} must be 0..255")
