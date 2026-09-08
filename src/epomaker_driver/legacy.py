"""YC3121/CommonKbYc500 configuration, isolated from YC3123 opcode collisions.

Evidence, USB routing and remaining features: docs/yc3121.md.
"""

from . import codec
from .errors import ProtocolError, UnsupportedDevice
from .models import model_by_id, validate_sleep_times

YC3121_IDS = (1379, 1723)
COMMANDS = frozenset(
    (
        "identify",
        "status",
        "matrix",
        "key",
        "bind-key",
        "bind-media",
        "bind-mouse",
        "bind-macro",
        "get-light",
        "light",
        "get-macro",
        "macro",
        "disable-key",
        "profile",
        "get-sleep",
        "sleep",
        "debounce",
        "get-auto-os",
        "auto-os",
    )
)


class LegacyKeyboard:
    def __init__(self, transport):
        if transport.kind != "usb":
            raise UnsupportedDevice("YC3121 migration currently requires direct USB")
        self.transport = transport
        self.identity = None
        self.model = None

    def identify(self):
        def operation():
            raw = self.transport.exchange(codec.identify_request(), expected=0x8F)
            if len(raw) != 64 or raw[0] != 0x8F:
                raise ProtocolError("invalid YC3121 identity response")
            mid = int.from_bytes(raw[1:5], "little")
            if mid not in YC3121_IDS:
                raise UnsupportedDevice("This YC3121 model has no migrated configuration protocol")
            # This family reads USB firmware separately; 0x8f version offsets are not assumed.
            rev = self.transport.exchange(codec.packet([0x80]), expected=0x80)
            if len(rev) != 64 or rev[0] != 0x80:
                raise ProtocolError("invalid YC3121 firmware response")
            version = int.from_bytes(rev[1:3], "little")
            if version in (0, 0xFFFF):
                raise ProtocolError("YC3121 did not report a normal firmware version")
            self.model = model_by_id(mid)
            self.identity = {"device_id": mid, "usb_version": version, "is_boot": None}
            return {**self.identity, "model": self.model["displayName"]}

        # A failed fresh identification must not leave a previously validated identity cached.
        self.identity = self.model = None
        return self.transport.transaction(operation)

    def _supported(self):
        if self.identity is None:
            self.identify()

    def _query(self, opcode):
        self._supported()
        reply = self.transport.exchange(codec.packet([opcode]), expected=opcode)
        if len(reply) != 64 or reply[0] != opcode:
            raise ProtocolError("invalid YC3121 settings response")
        return reply

    def _send(self, command):
        self._supported()
        self.transport.send(command)
        self.transport.sleep(0.5)  # inherited defaultVendorSleepTime, ef0a2b57.js

    def _profile(self, profile):
        self._supported()
        return codec.bounded(profile, self.model["layer"] - 1, "profile")

    def get_profile(self):
        value = self._query(0x85)[1]
        if value >= self.model["layer"]:
            raise ProtocolError("YC3121 returned an invalid profile")
        return value

    def set_profile(self, profile):
        self._profile(profile)

        def operation():
            self._send(codec.packet([5, profile]))
            if self.get_profile() != profile:
                raise ProtocolError("profile readback differs")

        self.transport.transaction(operation)

    def read_matrix(self, profile=0, *, fn=False, os_mode=0):
        self._profile(profile)
        if fn or os_mode != 0:
            raise UnsupportedDevice("YC3121 Fn and OS matrix selection are not migrated yet")

        def operation():
            pages = []
            for page in range(8):
                raw = self.transport.exchange(codec.packet([0x89, profile, page]))
                if len(raw) != 64:
                    raise ProtocolError(f"incomplete YC3121 matrix page {page}")
                pages.append(raw)
            return b"".join(pages)

        return self.transport.transaction(operation)

    def set_key(self, slot, action, *, profile=0, fn=False, os_mode=0):
        self._profile(profile)
        codec.bounded(slot, 127, "slot")
        action = bytes(action)
        if len(action) != 4:
            raise ValueError("action must contain four bytes")
        if fn or os_mode != 0:
            raise UnsupportedDevice("YC3121 Fn and OS matrix selection are not migrated yet")
        command = codec.packet(bytes([0x13, profile, slot]) + bytes(5) + action)

        def operation():
            self._send(command)
            actual = self.read_matrix(profile)[slot * 4 : slot * 4 + 4]
            if actual != action:
                raise ProtocolError("key readback differs")
            return list(actual)

        return self.transport.transaction(operation)

    def write_matrix(self, matrix, profile=0):
        self._profile(profile)
        matrix = bytes(matrix)
        if len(matrix) != 512:
            raise ValueError("matrix must have 128 four-byte slots")

        def operation():
            previous = self.read_matrix(profile)
            for slot in range(128):
                start = slot * 4
                action = matrix[start : start + 4]
                if action != previous[start : start + 4]:
                    self._send(codec.packet(bytes([0x13, profile, slot]) + bytes(5) + action))
            if self.read_matrix(profile) != matrix:
                raise ProtocolError("matrix readback differs")

        self.transport.transaction(operation)

    def read_macro(self, slot):
        codec.bounded(slot, 255, "macro slot")
        self._supported()

        def operation():
            pages = []
            for page in range(4):
                raw = self.transport.exchange(codec.packet([0x8B, slot, page]))
                if len(raw) != 64:
                    raise ProtocolError(f"incomplete YC3121 macro page {page}")
                pages.append(raw)
            return b"".join(pages)

        return self.transport.transaction(operation)

    def write_macro(self, slot, data):
        data = bytes(data)
        # Same five-chunk layout as YC3123, but write opcode 0x16. Recompute checksum.
        # Send the zero tail too: vendor's nonzero-chunk count loses sparse/empty data.
        commands = [
            codec.packet(bytes([0x16]) + command[1:])
            for command in codec.macro_chunks(slot, data, full=True)
        ]
        self._supported()

        def operation():
            for command in commands:
                self.transport.send(command)
            self.transport.sleep(0.5)
            if self.read_macro(slot) != data:
                raise ProtocolError("macro readback differs")

        self.transport.transaction(operation)

    def get_light(self, *, side=False):
        if side:
            raise UnsupportedDevice("These YC3121 models have no side-light layout")
        result = codec.parse_light(self._query(0x87))
        result["speed"] += 1  # CommonKbYc500 inherits MAXSPEED=5, not YC3123's 4.
        return result

    def set_light(self, mode, **options):
        if options.get("side", False):
            raise UnsupportedDevice("These YC3121 models have no side-light layout")
        if mode == "off":
            raise UnsupportedDevice("YC3121 layout has no off effect; use brightness zero")
        # Vendor ce/ue layout: three pictures and mode-specific direction choices.
        maximum = {
            "wave": 3,
            "snake": 1,
            "kaleidoscope": 1,
            "line-wave": 1,
            "circle-wave": 1,
            "picture": 2,
            "music": 2,
        }.get(mode, 0)
        codec.bounded(options.get("option", 0), maximum, "lighting option")
        if mode in ("solid", "picture", "music", "screen"):
            codec.bounded(options.get("speed", 0), 0, "speed for this effect")
        command = bytearray(codec.light(mode, **options))
        command[2] += 1
        command = codec.packet(command, 8)
        self._supported()

        def operation():
            self.transport.send(command)
            self.transport.sleep(1.0)  # older setLightSetting explicitly waits 1000 ms
            actual = self.get_light()
            if actual["raw"][1:8] != list(command[1:8]):
                raise ProtocolError("lighting readback differs")
            return actual

        return self.transport.transaction(operation)

    def get_sleep(self):
        raw = self._query(0x92)
        # Unlike YC3123, the reply packs timers immediately after the opcode.
        return dict(
            zip(
                ("bluetooth", "dongle", "deep_bluetooth", "deep_dongle"),
                (int.from_bytes(raw[i : i + 2], "little") for i in (1, 3, 5, 7)),
                strict=True,
            )
        )

    def set_sleep(self, bt, dongle, deep_bt, deep_dongle=None):
        self._supported()
        values = (bt, dongle, deep_bt, deep_dongle)
        validate_sleep_times(self.identity["device_id"], values)
        command = codec.packet(
            bytes([0x12]) + bytes(7) + b"".join(value.to_bytes(2, "little") for value in values)
        )

        def operation():
            self._send(command)
            actual = self.get_sleep()
            if tuple(actual.values()) != values:
                raise ProtocolError("sleep readback differs")
            return actual

        return self.transport.transaction(operation)

    def get_debounce(self):
        return self._query(0x91)[2]

    def set_debounce(self, milliseconds):
        codec.bounded(milliseconds, 255, "debounce")

        def operation():
            self._send(codec.packet([0x11, 0, milliseconds]))
            if self.get_debounce() != milliseconds:
                raise ProtocolError("debounce readback differs")

        self.transport.transaction(operation)

    def get_auto_os(self):
        return self._query(0x97)[1] == 1

    def set_auto_os(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("enabled must be boolean")

        def operation():
            self._send(codec.packet([0x17, int(enabled)]))
            if self.get_auto_os() != enabled:
                raise ProtocolError("automatic OS selection readback differs")

        self.transport.transaction(operation)

    def status(self):
        self._supported()
        return {
            "identity": self.identity,
            "model": self.model["displayName"],
            "profiles": self.model["layer"],
            "profile": self.get_profile(),
            "capabilities": [
                "keymap",
                "profile",
                "sleep",
                "debounce",
                "auto-os",
                "macro",
                "lighting",
            ],
            "sleep": self.get_sleep(),
            "debounce": self.get_debounce(),
            "auto_os": self.get_auto_os(),
            "battery": self.transport.battery,
            "online": self.transport.online,
        }
