"""CH585 USB mouse configuration; recovered protocol in docs/ch585-protocol.md."""

from . import codec, mouse_codec
from .errors import ProtocolError, UnsupportedDevice
from .models import data_file, model_by_id

PRODUCTS = {0x503A: (3961, 3304, 3929), 0x5043: (3303, 3919)}
COMMANDS = frozenset(
    (
        "identify",
        "status",
        "profile",
        "mouse-matrix",
        "mouse-key",
        "get-mouse-dpi",
        "mouse-dpi",
        "mouse-rate",
        "get-mouse-settings",
        "mouse-setting",
        "get-macro",
        "macro",
        "bind-key",
        "bind-media",
        "bind-mouse",
        "bind-macro",
        "disable-key",
        "mouse-bind",
    )
)


class Mouse:
    def __init__(self, transport, *, product_id):
        if product_id not in PRODUCTS or transport.kind != "usb":
            raise UnsupportedDevice("CH585 mice require a supported USB command interface")
        self.transport = transport
        self.product_id = product_id
        self.identity = None
        self.model = None

    def identify(self):
        self.identity = self.model = None
        raw = self.transport.exchange(codec.packet([0x8F]), expected=0x8F)
        value = mouse_codec.identity(raw)
        if value["device_id"] not in PRODUCTS[self.product_id]:
            raise UnsupportedDevice("mouse internal ID does not match the supported USB product")
        self.model = model_by_id(value["device_id"])
        self.identity = value
        return {**value, "model": self.model["displayName"]}

    def _supported(self):
        if self.identity is None:
            self.identify()
        if self.identity["device_id"] not in PRODUCTS[self.product_id]:
            raise UnsupportedDevice("mouse identity is not supported")

    def _query(self, payload, expected=None):
        self._supported()
        return self.transport.exchange(codec.packet(payload), expected=expected)

    def _write(self, command):
        self._supported()
        self.transport.send(command)
        self.transport.sleep(0.1)

    def get_profile(self):
        value = self._query([0x82], 0x82)[1]
        if value > 7:
            raise ProtocolError("mouse returned an invalid profile")
        return value

    def set_profile(self, profile):
        codec.bounded(profile, 7, "mouse profile")

        def operation():
            self.identify()
            self._write(codec.packet([2, profile]))
            if self.get_profile() != profile:
                raise ProtocolError("mouse profile readback differs")
            return {"profile": profile}

        return self.transport.transaction(operation)

    def read_matrix(self, profile=0):
        codec.bounded(profile, 7, "mouse profile")
        # The entire 16-slot matrix is raw data, without an echoed opcode.
        return self._query([0x81, profile, 1])

    def set_key(self, slot, action, *, profile=None):
        codec.bounded(slot, 15, "mouse slot")
        if not isinstance(action, bytes) or len(action) != 4:
            raise ValueError("mouse action must be exactly four raw bytes")
        if profile is not None:
            codec.bounded(profile, 7, "mouse profile")

        def operation():
            self.identify()
            defaults = data_file("ch585-matrices.json")[str(self.identity["device_id"])]
            if not any(defaults[slot * 4 : slot * 4 + 4]):
                raise ValueError("mouse slot is not present in this model layout")
            active = self.get_profile()
            if profile is not None and profile != active:
                raise ValueError("select the requested mouse profile before editing its buttons")
            before = self.read_matrix(active)
            wanted = before[: slot * 4] + action + before[slot * 4 + 4 :]
            if self.get_profile() != active:
                raise ProtocolError("mouse profile changed before button write")
            if wanted != before:
                self._write(codec.packet(bytes([0, slot]) + bytes(6) + action))
            if self.read_matrix(active) != wanted or self.get_profile() != active:
                raise ProtocolError("mouse button/profile readback differs")
            return {"profile": active, "slot": slot, "action": action.hex()}

        return self.transport.transaction(operation)

    def get_dpi(self, profile=0):
        codec.bounded(profile, 7, "mouse profile")
        value = mouse_codec.dpi(self._query([0x90, profile], 0x90))
        value["requested_profile"] = profile
        return value

    def _dpi_value(self, value):
        spec = self.model["dpi"]
        codec.bounded(value, spec["max"], "DPI")
        if value == 0:
            return
        if value < spec["min"]:
            raise ValueError("DPI is below the model minimum")
        step = spec["delt"]
        ranges = self.model.get("other", {}).get("dpiStepRanges")
        if ranges:
            step = next(
                row["step"]
                for i, row in enumerate(ranges)
                if value >= row["min"] and (value < row["max"] or i == len(ranges) - 1)
            )
        else:
            sensor = self.model["sensor"]
            threshold = (
                10000 if sensor == "PAW3311" else 26000 if sensor == "PAW3395" else spec["max"] / 2
            )
            step *= 1 if value < threshold else 4 if sensor == "PAW3311" and value >= 12000 else 2
        if value % step:
            raise ValueError(f"DPI must use {step}-unit increments at this value")

    def set_dpi(self, profile=0, *, current=None, slot=None, x=None, y=None, rgb=None):
        codec.bounded(profile, 7, "mouse profile")
        if all(value is None for value in (current, slot, x, y, rgb)):
            raise ValueError("choose a DPI level or setting to change")

        def operation():
            self.identify()
            count = self.model["dpi"]["count"]
            if slot is not None:
                codec.bounded(slot, count - 1, "DPI slot")
            if current is not None:
                codec.bounded(current, count - 1, "current DPI slot")
            for value in (x, y):
                if value is not None:
                    self._dpi_value(value)
            before = self.get_dpi(profile)
            command = mouse_codec.dpi_command(
                bytes(before["raw"]),
                profile=profile,
                current=current,
                slot=slot,
                x=x,
                y=y,
                rgb=rgb,
                count=count,
            )
            desired = mouse_codec.dpi(bytes([0x90]) + command[1:])
            enabled = [
                i for i, row in enumerate(desired["levels"][:count]) if row["x"] and row["y"]
            ]
            if not enabled:
                raise ValueError("at least one DPI level must remain enabled")
            if slot is not None:
                row = desired["levels"][slot]
                if bool(row["x"]) != bool(row["y"]):
                    raise ValueError("disable a DPI level by setting both X and Y to zero")
            active = desired["current"]
            if current is None and slot == active and active not in enabled:
                command = mouse_codec.dpi_command(
                    bytes([0x90]) + command[1:], profile=profile, current=enabled[0]
                )
                active = enabled[0]
            if active not in enabled:
                raise ValueError("current DPI level must be an enabled catalog slot")
            self._write(command)
            actual = self.get_dpi(profile)
            raw = bytes(actual["raw"])
            if raw[2:4] != command[2:4] or raw[8:] != command[8:]:
                raise ProtocolError("mouse DPI readback differs, including untouched levels")
            return actual

        return self.transport.transaction(operation)

    def set_rate(self, hz):
        command = mouse_codec.rate_command(hz)

        def operation():
            self.identify()
            if hz > (8000 if self.product_id == 0x503A else 1000):
                raise ValueError("report rate exceeds this USB model interface limit")
            self._write(command)
            actual = mouse_codec.parse_rate(self._query([0x88], 0x88))
            if actual != hz:
                raise ProtocolError("mouse report-rate readback differs")
            return {"report_rate": actual}

        return self.transport.transaction(operation)

    def _read_macro_pages(self, slot):
        pages = []
        for page in range(4):
            raw = self.transport.exchange(codec.packet([0x83, slot, page]))
            if len(raw) != 64:
                raise ProtocolError(f"mouse macro page {page} must be exactly 64 bytes")
            pages.append(bytes(raw))
        return b"".join(pages)

    def read_macro(self, slot):
        """Read all four raw 64-byte pages of one 256-byte mouse macro."""

        codec.bounded(slot, 49, "mouse macro slot")

        def operation():
            self.identify()
            profile = self.get_profile()
            data = self._read_macro_pages(slot)
            if self.get_profile() != profile:
                raise ProtocolError("mouse profile changed during macro read")
            return data

        return self.transport.transaction(operation)

    def write_macro(self, slot, data):
        """Replace one raw 256-byte macro using all five contiguous chunks."""

        codec.bounded(slot, 49, "mouse macro slot")
        if not isinstance(data, bytes) or len(data) != 256:
            raise ValueError("mouse macro data must be exactly 256 bytes")

        def operation():
            self.identify()
            profile = self.get_profile()
            before = self._read_macro_pages(slot)
            if self.get_profile() != profile:
                raise ProtocolError("mouse profile changed before macro write")
            if before == data:
                return {"slot": slot, "profile": profile, "changed": False}
            try:
                for chunk in range(5):
                    if self.get_profile() != profile:
                        raise ProtocolError("mouse profile changed before macro write")
                    payload = data[chunk * 56 : (chunk + 1) * 56].ljust(56, b"\0")
                    command = codec.packet(
                        bytes([3, slot, chunk, 56, chunk == 4, 0, 0, 0]) + payload
                    )
                    self._write(command)
                actual = self._read_macro_pages(slot)
                if actual != data:
                    raise ProtocolError("mouse macro readback differs")
                if self.get_profile() != profile:
                    raise ProtocolError("mouse profile changed during macro write")
            except (Exception, KeyboardInterrupt) as error:
                raise ProtocolError(
                    f"mouse macro slot {slot} failed during chunk {chunk} or verification: "
                    f"{error}; macro may be partially written"
                ) from error
            return {"slot": slot, "profile": profile, "changed": True}

        return self.transport.transaction(operation)

    def settings(self):
        return mouse_codec.aggregate(self._query([0x9F], 0x9F))

    def setting_options(self):
        """Vendor mouse UI capabilities, separate from keyboard catalog flags."""
        self._supported()
        lod = {
            "PAW3950": ["0.7", "1", "2"],
            "PAW3955": ["0.7", "1", "2"],
            "PAW3395": ["1", "2"],
        }.get(self.model["sensor"], [])
        other = self.model.get("other", {})
        version = format(self.identity["usb_version"] or 0, "x")
        # Vendor Number(version.toString(16)): hex letters become NaN, not a version.
        low_latency = bool(
            other.get("lowLatency") and version.isdecimal() and int(version) > other["lowLatency"]
        )
        return {
            "lod_mm": lod,
            "low_latency": low_latency,
            "sleep_bt": not other.get("noShowBT", False),
        }

    def _setting_supported(self, name, value=None):
        options = self.setting_options()
        if name == "lod":
            if not options["lod_mm"]:
                raise UnsupportedDevice("this mouse sensor has no vendor LOD selector")
            if value is not None:
                codec.bounded(value, len(options["lod_mm"]) - 1, "LOD index")
        if name in ("low_latency", "sleep_bt") and not options[name]:
            raise UnsupportedDevice(f"{name} is unavailable for this mouse/firmware")

    def get_setting(self, name):
        command = mouse_codec.setting_query(name)
        self._setting_supported(name)
        return mouse_codec.parse_setting(
            name, self.transport.exchange(command, expected=command[0])
        )

    def set_setting(self, name, value):
        command = mouse_codec.setting_command(name, value)

        def operation():
            self.identify()
            self._setting_supported(name, value)
            profile = self.get_profile()
            before = self.get_setting(name)
            if self.get_profile() != profile:
                raise ProtocolError("mouse profile changed before setting write")
            if before != value:
                self._write(command)
            actual = self.get_setting(name)
            if actual != value or self.get_profile() != profile:
                raise ProtocolError("mouse setting/profile readback differs")
            return {"setting": name, "value": actual, "profile": profile}

        return self.transport.transaction(operation)

    def status(self):
        def operation():
            identity = self.identify()
            profile = self.get_profile()
            result = {
                "identity": identity,
                "profile": profile,
                "settings": self.settings(),
                "dpi": self.get_dpi(profile),
                "matrix": self.read_matrix(profile).hex(),
                "capabilities": sorted(COMMANDS),
                "setting_options": self.setting_options(),
                "hardware_verified": False,
            }
            if self.get_profile() != profile:
                raise ProtocolError("mouse profile changed during status read")
            return result

        return self.transport.transaction(operation)
