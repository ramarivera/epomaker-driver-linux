"""Glyph/YC3123 packet encoders. Transport access lives in transport.py.

See docs/provenance.md for protocol evidence.
All offsets are in command payloads, BEFORE the HID report-ID prefix.
"""

import struct


def bounded(value, maximum, name):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"{name} must be an integer in 0..{maximum}")
    return value


def packet(payload, checksum_index=7):
    """Return the padded 64-byte command. Checksum covers header only."""
    p = bytearray(payload)
    if not 1 <= len(p) <= 64:
        raise ValueError("payload length must be 1..64")
    if checksum_index not in (7, 8, None):
        raise ValueError("checksum_index must be 7, 8 or None")
    p.extend(bytes(64 - len(p)))
    if checksum_index is not None:
        p[checksum_index] = 255 - (sum(p[:checksum_index]) & 255)
    return bytes(p)


def usb_report(command):
    if len(command) != 64:
        raise ValueError("command must be 64 bytes")
    return b"\x00" + command  # feature report 0; HIDAPI/hidraw API buffer


def bluetooth_report(command):
    if len(command) != 64:
        raise ValueError("command must be 64 bytes")
    return b"\x06\x55" + command  # report 6 + routing marker + command


def identify_request():
    return packet([0x8F])


def parse_identity(command_response):
    p = bytes(command_response)
    if len(p) < 12 or p[0] != 0x8F:
        raise ValueError("expected an unwrapped 0x8f response of at least 12 bytes")
    return {
        "device_id": struct.unpack_from("<I", p, 1)[0],
        "usb_version": struct.unpack_from("<H", p, 7)[0],
        "is_boot": p[9] == 1,
        "light_sync": p[11] == 1,
    }


def key_matrix_read(profile, page, mode=0, *, profile_max=2):
    return packet(
        [
            0x8A,
            bounded(profile, bounded(profile_max, 255, "profile maximum"), "profile"),
            255,
            bounded(page, 7, "page"),
            bounded(mode, 255, "mode"),
        ]
    )


def single_key(profile, slot, action, commit=True, mode=0, *, profile_max=2):
    action = bytes(action)
    if len(action) != 4:
        raise ValueError("action must contain four bytes")
    return packet(
        bytes(
            [
                0x0A,
                bounded(profile, bounded(profile_max, 255, "profile maximum"), "profile"),
                bounded(slot, 127, "slot"),
                0,
                0,
                int(bool(commit)),
                bounded(mode, 255, "mode"),
                0,
            ]
        )
        + action
    )


def sleep_times(bt, dongle, deep_bt, deep_dongle):
    values = [bounded(v, 64800, "sleep seconds") for v in (bt, dongle, deep_bt, deep_dongle)]
    return packet(bytes([0x11]) + bytes(7) + struct.pack("<4H", *values))


def solid_light(rgb, brightness=4):
    """Main backlight solid-color example; other modes have different option rules."""
    bounded(rgb, 0xFFFFFF, "rgb")
    bounded(brightness, 4, "brightness")
    if rgb == 0xFFFFFF:
        rgb = 0xFAFFFA  # vendor substitutes this value for pure white
    return packet([7, 1, 4, brightness, 7, rgb >> 16, (rgb >> 8) & 255, rgb & 255], 8)


def clock_command(year, month, day, hour, minute, second):
    import datetime

    datetime.datetime(year, month, day, hour, minute, second)
    return packet(
        bytes([0x28]) + bytes(7) + struct.pack(">H5B", year, month, day, hour, minute, second)
    )


def system_info(values):
    gib = 1024**3
    rounded = []
    for key in (
        "disk_available",
        "disk_total",
        "memory_used",
        "memory_total",
        "network_up",
        "network_down",
    ):
        value = values[key]
        if type(value) is not int or value < 0:
            raise ValueError(f"{key} must be a nonnegative byte count")
        rounded.append(bounded((value + gib // 2) // gib, 65535, key + " GiB"))
    cpu = bounded(values["cpu_usage"], 100, "CPU usage")
    temperature = values["cpu_temperature"]
    temperature = 0 if temperature is None else bounded(temperature, 255, "CPU temperature")
    return packet(
        bytes([0x22])
        + bytes(7)
        + struct.pack("<4HBB2H", *rounded[:4], cpu, temperature, *rounded[4:])
    )


def macro_keyboard_event(hid_usage, down, delay_ms):
    if type(down) is not bool:
        raise ValueError("down must be a boolean")
    bounded(hid_usage, 239, "hid usage")
    if hid_usage < 4:
        raise ValueError("keyboard HID usage must be at least 4")
    bounded(delay_ms, 65535, "delay_ms")
    if delay_ms == 0:
        raise ValueError("zero-delay encoding is ambiguous in the bundled decoder")
    flag = 128 if down else 0
    return (
        bytes([hid_usage, flag | delay_ms])
        if delay_ms <= 127
        else bytes([hid_usage, flag]) + struct.pack("<H", delay_ms)
    )


def rgb565_column_major(rows):
    if not rows or not rows[0] or any(len(r) != len(rows[0]) for r in rows):
        raise ValueError("rows must be a nonempty rectangular RGB integer grid")
    result = bytearray()
    for x in range(len(rows[0])):
        for row in rows:
            rgb = bounded(row[x], 0xFFFFFF, "rgb")
            r, g, b = rgb >> 16, (rgb >> 8) & 255, rgb & 255
            result.extend(struct.pack(">H", ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)))
    return bytes(result)


def screen_prepare(data_length, bounds, frame=0, frames=1, delay=0, extra=0, *, size=(428, 142)):
    """0xa5 is a transfer handshake, NOT a read-only screen query."""
    bounded(data_length, 0xFFFFFFFF, "data length")
    if len(bounds) != 4:
        raise ValueError("bounds must be left,top,right,bottom")
    left, top, right, bottom = bounds
    width, height = (bounded(v, 65535, "display dimension") for v in size)
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError(f"bounds must fit the {width}x{height} display")
    for v in (frame, frames, delay, extra):
        bounded(v, 255, "frame metadata")
    if frames == 0 or frame >= (5 if frames == 1 else frames):
        raise ValueError("choose still bank 0..4 or an index below the animation frame count")
    p = bytearray(64)
    p[:7] = bytes([0xA5, frame, frames, delay, data_length & 255, (data_length >> 8) & 255, 0])
    p[8:12] = bytes(v & 255 for v in bounds)
    p[12:16] = bytes(v >> 8 for v in bounds)
    p[16:19] = bytes([(data_length >> 16) & 255, data_length >> 24, extra])
    return packet(p)


def screen_chunks(data, frame=0, frames=1, delay=0):
    data = bytes(data)
    for v in (frame, frames, delay):
        bounded(v, 255, "frame metadata")
    if frames == 0 or frame >= (5 if frames == 1 else frames) or not data or len(data) > 56 * 65536:
        raise ValueError("invalid frame metadata or screen payload length")
    for index, start in enumerate(range(0, len(data), 56)):
        chunk = data[start : start + 56]
        yield packet(
            bytes([0x25, frame, frames, delay, index & 255, index >> 8, len(chunk), 0]) + chunk
        )


LIGHT_MODES = {
    "off": 0,
    "solid": 1,
    "breathing": 2,
    "neon": 3,
    "wave": 4,
    "ripple": 5,
    "raindrop": 6,
    "snake": 7,
    "reactive": 8,
    "convergence": 9,
    "sine": 10,
    "kaleidoscope": 11,
    "line-wave": 12,
    "picture": 13,
    "laser": 14,
    "circle-wave": 15,
    "dazzling": 16,
    "rain": 17,
    "meteor": 18,
    "reactive-off": 19,
    "screen": 21,
    "music": 22,
}
DEFAULT_LIGHT_PALETTE = (0xFF0000, 0xFF8000, 0xFFFF00, 0x00FF00, 0x00FFFF, 0x0000FF, 0xFF00FF)
SIDE_MODES = {"off": 0, "solid": 1, "breathing": 2, "neon": 3, "wave": 4, "snake": 5}


def light(
    mode,
    *,
    rgb=0xFFFFFF,
    brightness=4,
    speed=0,
    option=0,
    rainbow=False,
    side=False,
    side_speed_max=3,
    normal=7,
    dazzle=8,
):
    modes = SIDE_MODES if side else LIGHT_MODES
    if mode not in modes:
        raise ValueError("unsupported light mode")
    bounded(rgb, 0xFFFFFF, "rgb")
    bounded(brightness, 4, "brightness")
    bounded(speed, bounded(side_speed_max, 4, "side speed maximum") if side else 4, "speed")
    bounded(option, 4 if mode == "picture" else 15, "option")
    flags = (option << 4) | bounded(dazzle if rainbow else normal, 15, "color flag")
    if mode == "picture":
        flags = option << 4
    elif mode == "music":
        flags = (option << 4) | (0 if rainbow else 4)
    elif mode == "screen":
        flags = 0
    elif side and mode == "neon":
        flags = 8
    rgb = 0xFAFFFA if rgb == 0xFFFFFF else rgb
    red, green, blue = rgb >> 16, (rgb >> 8) & 255, rgb & 255
    if mode == "picture":
        red, green, blue = 0, 200, 200
    return packet(
        [
            8 if side else 7,
            modes[mode],
            speed if side else 4 - speed,
            brightness,
            flags,
            red,
            green,
            blue,
        ],
        8,
    )


def parse_light(data, *, side=False, dazzle=8, palette=DEFAULT_LIGHT_PALETTE):
    from .errors import ProtocolError

    if len(data) != 64 or data[0] != (0x88 if side else 0x87):
        raise ProtocolError("unexpected lighting response")
    modes = SIDE_MODES if side else LIGHT_MODES
    mode = next((k for k, v in modes.items() if v == data[1]), "unknown")
    rgb = int.from_bytes(data[5:8], "big")
    color_mode = data[4] & 15
    if color_mode < len(palette):
        rgb = palette[color_mode]
    if rgb == 0xFAFFFA:
        rgb = 0xFFFFFF
    return {
        "mode": mode,
        "mode_id": data[1],
        "rgb": rgb,
        "brightness": data[3],
        "speed": data[2] if side else 4 - data[2],
        "option": data[4] >> 4,
        "rainbow": color_mode == (0 if mode == "music" else dazzle),
        "raw": list(data),
    }


def matrix_chunks(matrix, profile=0, mode=0, *, profile_max=2):
    matrix = bytes(matrix)
    if len(matrix) != 512:
        raise ValueError("matrix must have 128 four-byte entries")
    bounded(profile, bounded(profile_max, 255, "profile maximum"), "profile")
    bounded(mode, 255, "mode")
    for index, start in enumerate(range(0, 512, 56)):
        chunk = matrix[start : start + 56]
        yield packet(
            bytes([0x0A, profile, 255, index, len(chunk), int(start + 56 >= 512), mode, 0]) + chunk
        )


def fn_read(layer=0, page=0, os_mode=0):
    return packet(
        [
            0x90,
            bounded(os_mode, 3, "OS selector"),
            bounded(layer, 0, "Fn layer"),
            255,
            bounded(page, 7, "page"),
        ]
    )


def fn_single(slot, action, *, layer=0, os_mode=0):
    if len(action) != 4:
        raise ValueError("action must have four bytes")
    return packet(
        bytes(
            [
                0x10,
                bounded(os_mode, 3, "OS selector"),
                bounded(layer, 0, "Fn layer"),
                bounded(slot, 127, "slot"),
                0,
                0,
                0,
                0,
            ]
        )
        + bytes(action)
    )


def macro_data(repeat, events):
    bounded(repeat, 65535, "repeat count")
    if not isinstance(events, list) or any(
        not isinstance(event, dict) or set(event) != {"hid_usage", "down", "delay_ms"}
        for event in events
    ):
        raise ValueError("events must be a list of hid_usage/down/delay_ms objects")
    result = struct.pack("<H", repeat) + b"".join(macro_keyboard_event(**event) for event in events)
    if len(result) > 256:
        raise ValueError("macro exceeds 256-byte storage")
    return result.ljust(256, b"\0")


def macro_chunks(slot, data, *, full=False):
    bounded(slot, 255, "macro slot")
    if len(data) != 256:
        raise ValueError("macro must be exactly 256 bytes")
    # Use the highest nonzero chunk, not the count of nonzero chunks: preserves holes.
    last = 4 if full else max((i for i, v in enumerate(data) if v), default=0) // 56
    for index in range(last + 1):
        yield packet(
            bytes([0x0B, slot, index, 56, int(index == last), 0, 0, 0])
            + data[index * 56 : (index + 1) * 56]
        )


def picture_chunks(colors, picture=0):
    bounded(picture, 4, "picture")
    if len(colors) != 378:
        raise ValueError("picture requires 126 RGB triples (378 bytes)")
    for index in range(7):
        chunk = bytes(colors[index * 56 : (index + 1) * 56])
        yield packet(bytes([0x0C, picture, 255, index, len(chunk), int(index == 6), 0, 0]) + chunk)


def parse_sleep(data):
    from .errors import ProtocolError

    if len(data) != 64 or data[0] != 0x91:
        raise ProtocolError("unexpected sleep response")
    return dict(
        zip(
            ("bluetooth", "dongle", "deep_bluetooth", "deep_dongle"),
            struct.unpack_from("<4H", data, 8),
            strict=True,
        )
    )
