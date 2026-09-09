"""High-level keyboard configuration with explicit model/operation gates."""

from __future__ import annotations

import datetime

from . import codec, versions
from .errors import ProtocolError, ResponseTimeout, UnsupportedDevice
from .live_lighting import frame_packets
from .models import (
    RT100_PRO_IDS,
    RY6602_IDS,
    RY6602_SCREEN_IDS,
    RY6602_SIDE_IDS,
    display_spec,
    light_encoding,
    model_by_id,
    validate_sleep_times,
)


class Keyboard:
    def __init__(self, transport):
        self.transport = transport
        self.identity = None
        self.model = None

    def identify(self):
        self.identity = codec.parse_identity(
            self.transport.exchange(codec.identify_request(), expected=0x8F)
        )
        self.model = model_by_id(self.identity["device_id"])
        return {**self.identity, "model": self.model["displayName"]}

    def _supported(self):
        if self.identity is None:
            self.identify()
        if self.identity["device_id"] not in (2895, 3059, 3223, *RT100_PRO_IDS, *RY6602_IDS):
            raise UnsupportedDevice("This model has no migrated configuration protocol")
        if self.identity["is_boot"]:
            raise UnsupportedDevice("Device is in bootloader mode")

    def _check_commands(self, commands):
        self._supported()
        # RT85 inherits this protocol but does not expose every shared operation.
        # Display limits and the remaining capability gaps are in docs/rt85.md.
        if self.identity["device_id"] == 2895:
            for command in commands:
                if command[0] not in (
                    1,
                    4,
                    7,
                    8,
                    9,
                    12,
                    0x17,
                    10,
                    11,
                    16,
                    0x11,
                    0x27,
                    0x28,
                    0x84,
                    0x87,
                    0x88,
                    0x89,
                    0x8C,
                    0x97,
                    0x8A,
                    0x8B,
                    0x90,
                    0x91,
                    0xA5,
                ):
                    raise UnsupportedDevice(
                        "RT85 currently supports keymaps, Fn layers, macros, profiles, sleep, display, lighting and OS controls"
                    )

        if self.identity["device_id"] in (3223, *RT100_PRO_IDS):
            # RT75 display/light metadata differs; migrated operations: docs/rt75.md.
            allowed = (
                1,
                7,
                12,
                0x22,
                0x27,
                0x28,
                0x87,
                0x8C,
                0xA5,
                4,
                6,
                9,
                10,
                11,
                16,
                0x11,
                0x17,
                0x84,
                0x86,
                0x89,
                0x8A,
                0x8B,
                0x90,
                0x91,
                0x97,
            )
            if any(command[0] not in allowed for command in commands):
                raise UnsupportedDevice(
                    "RT75 and RT100 PRO support keymaps, Fn, macros, profiles, sleep, debounce, OS controls, main lighting and display"
                )

        if self.identity["device_id"] in RY6602_IDS:
            allowed = (
                1,
                7,
                12,
                0x87,
                0x8C,
                4,
                6,
                9,
                10,
                11,
                16,
                0x11,
                0x17,
                0x84,
                0x86,
                0x89,
                0x8A,
                0x8B,
                0x90,
                0x91,
                0x97,
            )
            if self.identity["device_id"] in RY6602_SIDE_IDS:
                allowed += (8, 0x88)
            if self.identity["device_id"] in RY6602_SCREEN_IDS:
                allowed += (0xA9,)
            if any(command[0] not in allowed for command in commands):
                raise UnsupportedDevice(
                    "RY6602 supports keymaps, Fn, macros, profiles, sleep, lighting, debounce and OS controls"
                )

    def _profile_max(self):
        self._supported()
        return self.model["layer"] - 1

    def _query(self, command, *, expected=None):
        self._check_commands([command])
        return self.transport.exchange(command, expected=expected)

    def _write(self, commands):
        self._check_commands(commands)

        def operation():
            for command in commands:
                self.transport.send(command)
            self.transport.sleep(0.1)

        self.transport.transaction(operation)

    def status(self):
        self._supported()
        profile = self._query(codec.packet([0x84]), expected=0x84)[1]
        if self.identity["device_id"] in RY6602_IDS:
            return {
                "identity": self.identity,
                "model": self.model["displayName"],
                "profile": profile,
                "profiles": self.model["layer"],
                "battery": self.transport.battery,
                "online": self.transport.online,
                "capabilities": [
                    "keymap",
                    "fn",
                    "macro",
                    "profile",
                    "debounce",
                    "os",
                    "sleep",
                    "lighting",
                ]
                + (["display"] if self.identity["device_id"] in RY6602_SCREEN_IDS else []),
                "display": display_spec(self.identity["device_id"])
                if self.identity["device_id"] in RY6602_SCREEN_IDS
                else None,
                "light": self.get_light(),
                "side_light": self.get_light(side=True)
                if self.identity["device_id"] in RY6602_SIDE_IDS
                else None,
                "sleep": self.get_sleep(),
                "debounce": self._query(codec.packet([0x86]), expected=0x86)[1],
                "options": self.get_options(),
                "auto_os": self.get_auto_os(),
            }
        if self.identity["device_id"] == 2895:
            return {
                "identity": self.identity,
                "model": self.model["displayName"],
                "profile": profile,
                "profiles": self.model["layer"],
                "battery": self.transport.battery,
                "online": self.transport.online,
                "capabilities": [
                    "keymap",
                    "fn",
                    "macro",
                    "profile",
                    "sleep",
                    "display",
                    "lighting",
                    "os",
                ],
                "light": self.get_light(),
                "side_light": self.get_light(side=True),
                "options": self.get_options(),
                "auto_os": self.get_auto_os(),
                "sleep": self.get_sleep(),
                "display": display_spec(2895),
            }
        if self.identity["device_id"] in (3223, *RT100_PRO_IDS):
            return {
                "identity": self.identity,
                "model": self.model["displayName"],
                "profile": profile,
                "profiles": self.model["layer"],
                "battery": self.transport.battery,
                "online": self.transport.online,
                "capabilities": [
                    "keymap",
                    "fn",
                    "macro",
                    "profile",
                    "sleep",
                    "debounce",
                    "os",
                    "lighting",
                    "display",
                ],
                "display": display_spec(self.identity["device_id"]),
                "light": self.get_light(),
                "debounce": self._query(codec.packet([0x86]), expected=0x86)[1],
                "sleep": self.get_sleep(),
                "options": self.get_options(),
                "auto_os": self.get_auto_os(),
            }
        rate = self._query(codec.packet([0x83]), expected=0x83)[2]
        debounce = (
            None
            if self.identity["device_id"] == 3059
            else self._query(codec.packet([0x86]), expected=0x86)[1]
        )
        return {
            "identity": self.identity,
            "model": self.model["displayName"],
            "profile": profile,
            "report_rate": {0: 8000, 1: 4000, 2: 2000, 3: 1000, 4: 500, 5: 250, 6: 125}.get(rate),
            "debounce": debounce,
            "battery": self.transport.battery,
            "online": self.transport.online,
            "light": self.get_light(),
            "sleep": self.get_sleep(),
        }

    def read_firmware_versions(self):
        """Read Glyph firmware components on demand without changing status/connect."""

        def operation():
            identity = self.identify()
            self._supported()
            if identity["device_id"] != 3059:
                raise UnsupportedDevice("firmware component reads currently support Glyph only")
            responses = {}
            for component in ("rf", "mled", "oled"):
                command = versions.version_request(component)
                response = self._query(command, expected=command[0])
                responses[component] = versions.parse_version(component, response)
            oled = responses["oled"]
            return {
                "usb": identity.get("usb_version") or None,
                "rf": responses["rf"] or None,
                "mled": responses["mled"] or None,
                "oled": oled["oled"],
                "flash": oled["flash"],
            }

        return self.transport.transaction(operation)

    def get_light(self, *, side=False):
        opcode = 0x88 if side else 0x87
        raw = self._query(codec.packet([opcode]), expected=opcode)
        _, dazzle, palette = light_encoding(self.identity["device_id"])
        return codec.parse_light(raw, side=side, dazzle=dazzle, palette=palette)

    def get_options(self):
        raw = self._query(codec.packet([0x89]), expected=0x89)
        return {
            "system": {0: "win", 1: "mac", 2: "ios", 3: "android"}.get(raw[1], "unknown"),
            "fn_layer": raw[2],
            "wasd_swap": raw[5] == 1,
            "raw": list(raw),
        }

    def set_options(self, *, system=None, wasd_swap=None):
        if system is not None and system not in ("win", "mac"):
            raise ValueError("Supported keyboards expose Windows and Mac system layers")
        if wasd_swap is not None and type(wasd_swap) is not bool:
            raise ValueError("wasd_swap must be boolean")

        def operation():
            # Preserve unrelated vendor option bytes, including unknown fields.
            raw = bytearray(self.get_options()["raw"][:7])
            raw[0] = 9
            if system is not None:
                raw[1] = 0 if system == "win" else 1
            if wasd_swap is not None:
                raw[5] = int(wasd_swap)
            self._write([codec.packet(raw)])
            actual = self.get_options()
            if actual["raw"][1:7] != list(raw[1:7]):
                raise ProtocolError("keyboard options readback differs")
            return actual

        return self.transport.transaction(operation)

    def get_auto_os(self):
        return self._query(codec.packet([0x97]), expected=0x97)[1] == 1

    def set_auto_os(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("enabled must be boolean")
        self._write([codec.packet([0x17, int(enabled)])])
        if self.get_auto_os() != enabled:
            raise ProtocolError("automatic OS selection readback differs")

    def write_fn_matrix(self, matrix, os_mode=0):
        matrix = bytes(matrix)
        if len(matrix) != 512:
            raise ValueError("Fn matrix must have 128 four-byte slots")
        codec.bounded(os_mode, 1, "OS selector")

        def operation():
            previous = self.read_matrix(fn=True, os_mode=os_mode)
            commands = [
                codec.fn_single(i, matrix[i * 4 : i * 4 + 4], os_mode=os_mode)
                for i in range(128)
                if matrix[i * 4 : i * 4 + 4] != previous[i * 4 : i * 4 + 4]
            ]
            self._write(commands)
            if self.read_matrix(fn=True, os_mode=os_mode) != matrix:
                raise ProtocolError("Fn matrix readback differs")

        self.transport.transaction(operation)

    def set_light(self, mode, **options):
        self._supported()
        side = options.get("side", False)
        speed_max = 3
        if self.identity["device_id"] in (3223, *RT100_PRO_IDS) and (side or mode == "off"):
            raise UnsupportedDevice(
                "RT75 and RT100 PRO have no side-light layout or explicit off mode"
            )
        if side and self.identity["device_id"] == 2895:
            # RT85's Kt layout differs from Glyph's Q: docs/rt85.md.
            if mode not in ("off", "solid", "breathing", "neon", "wave"):
                raise ValueError("RT85 side lighting supports off, solid, breathing, neon and wave")
            speed_max = 4 if mode == "wave" else 3
        if self.identity["device_id"] in RY6602_IDS:
            if side:
                if self.identity["device_id"] not in RY6602_SIDE_IDS or mode not in (
                    "wave",
                    "snake",
                    "breathing",
                    "off",
                ):
                    raise UnsupportedDevice(
                        "RY6602 side layout is absent or does not expose this effect"
                    )
            elif mode == "off":
                raise UnsupportedDevice(
                    "RY6602 main layout has no explicit off mode; use brightness zero"
                )
        normal, dazzle, _ = light_encoding(self.identity["device_id"])
        command = codec.light(
            mode, **options, side_speed_max=speed_max, normal=normal, dazzle=dazzle
        )
        self._write([command])
        actual = self.get_light(side=side)
        if actual["raw"][1:8] != list(command[1:8]):
            raise ProtocolError("lighting readback differs")
        return actual

    def get_sleep(self):
        result = codec.parse_sleep(self._query(codec.packet([0x91]), expected=0x91))
        if self.identity["device_id"] in RY6602_IDS:
            result.pop("deep_dongle")
        return result

    def set_sleep(self, bt, dongle, deep_bt, deep_dongle=None):
        self._check_commands([codec.packet([0x11])])
        validate_sleep_times(self.identity["device_id"], (bt, dongle, deep_bt, deep_dongle))

        def operation():
            ry = self.identity["device_id"] in RY6602_IDS
            command = bytearray(codec.sleep_times(bt, dongle, deep_bt, 0 if ry else deep_dongle))
            expected = dict(
                zip(
                    ("bluetooth", "dongle", "deep_bluetooth", "deep_dongle"),
                    (bt, dongle, deep_bt, deep_dongle),
                    strict=True,
                )
            )
            if ry:
                # Preserve the unexposed fourth uint16, including opaque values >64800.
                # Same packet layout, different UI capabilities: docs/ry6602.md.
                raw = self._query(codec.packet([0x91]), expected=0x91)
                original = codec.parse_sleep(raw)
                command[14:16] = raw[14:16]
                expected["deep_dongle"] = original["deep_dongle"]
            self._write([bytes(command)])
            actual = codec.parse_sleep(self._query(codec.packet([0x91]), expected=0x91))
            if actual != expected:
                raise ProtocolError("sleep readback differs")
            if ry:
                actual.pop("deep_dongle")
            return actual

        return self.transport.transaction(operation)

    def read_matrix(self, profile=0, *, fn=False, os_mode=0):
        self._supported()

        def operation():
            pages = []
            for page in range(8):
                command = (
                    codec.fn_read(profile, page, os_mode)
                    if fn
                    else codec.key_matrix_read(profile, page, profile_max=self._profile_max())
                )
                response = self.transport.exchange(command)
                if len(response) != 64:
                    raise ProtocolError(f"incomplete matrix page {page}; refusing a partial backup")
                pages.append(response)
            return b"".join(pages)

        return self.transport.transaction(operation)

    def set_key(self, slot, action, *, profile=0, fn=False, os_mode=0):
        command = (
            codec.fn_single(slot, action, layer=profile, os_mode=os_mode)
            if fn
            else codec.single_key(profile, slot, action, profile_max=self._profile_max())
        )
        self._write([command])
        actual = self.read_matrix(profile, fn=fn, os_mode=os_mode)[slot * 4 : slot * 4 + 4]
        if actual != bytes(action):
            raise ProtocolError("key readback differs from requested action")
        return list(actual)

    def write_matrix(self, matrix, profile=0):
        self._write(list(codec.matrix_chunks(matrix, profile, profile_max=self._profile_max())))
        actual = self.read_matrix(profile)
        if actual != bytes(matrix):
            raise ProtocolError("matrix readback differs from requested data")

    def set_profile(self, profile):
        codec.bounded(profile, self._profile_max(), "profile")
        self._write([codec.packet([4, profile])])
        actual = self._query(codec.packet([0x84]), expected=0x84)[1]
        if actual != profile:
            raise ProtocolError("profile readback differs")

    def set_debounce(self, milliseconds):
        if self.identity is None:
            self.identify()
        if self.identity["device_id"] == 3059:
            raise UnsupportedDevice("Glyph does not expose a debounce control")
        codec.bounded(milliseconds, 255, "debounce")
        self._write([codec.packet([6, milliseconds])])
        if self._query(codec.packet([0x86]), expected=0x86)[1] != milliseconds:
            raise ProtocolError("debounce readback differs")

    def read_macro(self, slot):
        codec.bounded(slot, 255, "macro slot")

        def operation():
            pages = [self._query(codec.packet([0x8B, slot, page])) for page in range(4)]
            if any(len(p) != 64 for p in pages):
                raise ProtocolError("incomplete macro response")
            return b"".join(pages)

        return self.transport.transaction(operation)

    def write_macro(self, slot, data):
        self._write(list(codec.macro_chunks(slot, data, full=True)))
        if self.read_macro(slot) != bytes(data):
            raise ProtocolError("macro readback differs")

    def write_picture(self, colors, picture=0):
        self._write(list(codec.picture_chunks(colors, picture)))
        if self.read_picture(picture) != bytes(colors):
            raise ProtocolError("custom RGB picture readback differs")

    def read_picture(self, picture=0):
        codec.bounded(picture, 4, "picture")

        def operation():
            pages = [self._query(codec.packet([0x8C, picture, 255, page])) for page in range(6)]
            if any(len(page) != 64 for page in pages):
                raise ProtocolError("incomplete custom RGB picture response")
            # Vendor writes only 126 RGB slots; the final six read bytes are not writable.
            return b"".join(pages)[:378]

        return self.transport.transaction(operation)

    def set_picture_key(self, picture, slot, rgb):
        codec.bounded(slot, 125, "RGB slot")
        codec.bounded(rgb, 0xFFFFFF, "rgb")

        def operation():
            colors = bytearray(self.read_picture(picture))
            colors[slot * 3 : slot * 3 + 3] = rgb.to_bytes(3, "big")
            self.write_picture(colors, picture)

        self.transport.transaction(operation)

    def sync_clock(self, value=None):
        value = value or datetime.datetime.now()
        self._write(
            [
                codec.clock_command(
                    value.year, value.month, value.day, value.hour, value.minute, value.second
                )
            ]
        )

    def sync_system_info(self, values):
        self._write([codec.system_info(values)])

    def toggle_display_language(self):
        # Vendor UI always sends 1; no current-language query or named setter was found.
        # Protocol provenance and exact command are documented in docs/display.md.
        self._write([codec.packet([0x27, 1])])

    def upload_screen(self, pixels, bounds, *, frame=0, frames=1, delay=0, progress=None):
        # Prepare all data/metadata before the first device mutation.
        self._supported()
        if frames > 1:
            self._require_wired_animation()
        spec = display_spec(self.identity["device_id"])
        if frames > spec["max_frames"]:
            raise ValueError("animation exceeds model display memory")
        prepare = codec.screen_prepare(
            len(pixels),
            bounds,
            frame,
            frames,
            delay,
            size=(spec["width"], spec["height"]),
            rgb_bits=spec["pixel_bytes"] * 8,
        )
        if len(pixels) != (bounds[2] - bounds[0]) * (bounds[3] - bounds[1]) * spec["pixel_bytes"]:
            raise ValueError("RGB payload does not match screen bounds")
        chunks = list(
            codec.screen_chunks(pixels, frame, frames, delay, rgb_bits=spec["pixel_bytes"] * 8)
        )
        self._transfer_screen(prepare, chunks, progress)

    def upload_animation(self, frames, delay, *, progress=None):
        self._supported()
        spec = display_spec(self.identity["device_id"])
        width, height, maximum = spec["width"], spec["height"], spec["max_frames"]
        if not 2 <= len(frames) <= maximum:
            raise ValueError(f"animation must contain 2..{maximum} frames")
        if any(len(frame) != width * height * spec["pixel_bytes"] for frame in frames):
            raise ValueError(f"animation frames must be complete {width}x{height} RGB images")
        self._require_wired_animation()
        prepare = codec.screen_prepare(
            len(frames[0]),
            (0, 0, width, height),
            0,
            len(frames),
            delay,
            size=(width, height),
            rgb_bits=spec["pixel_bytes"] * 8,
        )
        chunks = [
            chunk
            for index, frame in enumerate(frames)
            for chunk in codec.screen_chunks(
                frame, index, len(frames), delay, rgb_bits=spec["pixel_bytes"] * 8
            )
        ]
        self._transfer_screen(prepare, chunks, progress)

    def _require_wired_animation(self):
        """Match the vendor UI gate; see docs/releases/glyph-display-workflow-audit.md."""
        if self.identity["device_id"] == 3059 and getattr(self.transport, "kind", None) != "usb":
            raise UnsupportedDevice("Glyph animation uploads require a wired USB connection")

    def send_live_colors(self, colors):
        """Send one host-driven 21x6 RGB frame to a USB Glyph.

        The complete frame is encoded before acquiring the transport transaction,
        so invalid input cannot partially mutate the device. Each packet uses
        the transport's normal USB send delay; no extra post-frame delay is
        added.
        """
        self._supported()
        if self.identity["device_id"] != 3059:
            raise UnsupportedDevice("host-driven lighting currently supports Glyph only")
        if getattr(self.transport, "kind", None) != "usb":
            raise UnsupportedDevice("Glyph host-driven lighting requires a wired USB connection")
        if self.identity.get("is_boot"):
            raise UnsupportedDevice("host-driven lighting is unavailable in bootloader mode")
        if self.identity.get("light_sync") is not True:
            raise UnsupportedDevice("Glyph does not report host-driven lighting support")
        packets = frame_packets(colors)

        def operation():
            for packet in packets:
                self.transport.send(packet)
            return len(packets)

        return self.transport.transaction(operation)

    def _transfer_screen(self, prepare, chunks, progress):
        self._check_commands([prepare])

        def operation():
            for _ in range(11):
                try:
                    response = self.transport.exchange(prepare, read_delay=0.1, expected=prepare[0])
                except ResponseTimeout:
                    response = b""
                if len(response) >= 2 and response[1] == 1:
                    break
                self.transport.sleep(0.1)
            else:
                raise ProtocolError("screen transfer was not accepted")
            self.transport.sleep(0.1)
            for i, chunk in enumerate(chunks):
                self.transport.send(chunk, delay=0.005)
                if progress:
                    progress((i + 1) / len(chunks))

        self.transport.transaction(operation)
