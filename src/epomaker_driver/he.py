"""Read-capable HE60 Lite magnetic keyboard backend."""

from __future__ import annotations

from . import codec
from .device import Keyboard
from .errors import ProtocolError, UnsupportedDevice
from .he_lighting import HELightingMixin
from .he_modes import plan_mode, required_fields, validate_definition
from .he_settings import plan_update
from .magnetic import (
    assemble_pages,
    decode_field,
    encode_read,
    key_field,
    top_dead_zone_supported,
    travel_multiplier,
)
from .models import model_by_id
from .versions import parse_version, version_request

HE_PRODUCTS = {0x502C: 3727, 0x502E: 3759}
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
        "disable-key",
        "get-macro",
        "macro",
        "profile",
        "get-magnetic",
        "magnetic-key",
        "magnetic-mode",
        "get-options",
        "options",
        "get-auto-os",
        "auto-os",
        "debounce",
        "get-sleep",
        "sleep",
        "get-light",
        "light",
        "get-picture",
        "picture",
        "picture-key",
    )
)
OPCODES = frozenset(
    (
        0x04,
        0x06,
        0x07,
        0x09,
        0x0A,
        0x0B,
        0x0C,
        0x10,
        0x11,
        0x17,
        0x65,
        0x80,
        0x84,
        0x86,
        0x87,
        0x8C,
        0x89,
        0x8A,
        0x8B,
        0x8F,
        0x90,
        0x91,
        0x97,
        0xE5,
    )
)


class HEKeyboard(HELightingMixin, Keyboard):
    def __init__(self, transport, *, product_id):
        super().__init__(transport)
        if product_id not in HE_PRODUCTS:
            raise UnsupportedDevice("unsupported HE60 Lite USB product")
        self.product_id = product_id
        self.expected_id = HE_PRODUCTS[product_id]

    def identify(self):
        self.identity = None
        self.model = None
        identity = codec.parse_identity(
            self.transport.exchange(codec.identify_request(), expected=0x8F)
        )
        if identity["device_id"] != self.expected_id:
            raise UnsupportedDevice("HE60 Lite internal ID does not match USB product")
        if identity["is_boot"]:
            raise UnsupportedDevice("HE60 Lite is in bootloader mode")
        self.identity = identity
        self.model = model_by_id(identity["device_id"])
        return {**identity, "model": self.model["displayName"]}

    def _supported(self):
        if self.identity is None:
            self.identify()
        if self.identity["device_id"] != self.expected_id or self.identity["is_boot"]:
            raise UnsupportedDevice("HE60 Lite identity is not supported")

    def _check_commands(self, commands):
        self._supported()
        if any(command[0] not in OPCODES for command in commands):
            raise UnsupportedDevice("operation is not migrated for HE60 Lite")
        if self.expected_id != 3727 and any(command[0] in (0x06, 0x86) for command in commands):
            raise UnsupportedDevice("debounce is unavailable on wireless HE60 Lite")
        if self.expected_id != 3759 and any(command[0] in (0x11, 0x91) for command in commands):
            raise UnsupportedDevice("sleep is unavailable on wired HE60 Lite")
        if self.expected_id != 3759 and any(command[0] == 0x80 for command in commands):
            raise UnsupportedDevice("RF version is unavailable on wired HE60 Lite")

    def read_matrix(self, profile=0, *, fn=False, os_mode=0, mode=0):
        self._supported()
        codec.bounded(profile, 1, "profile")
        if fn:
            if profile != 0 or mode != 0:
                raise ValueError("Fn reads use layer 0 and submode 0")
            codec.bounded(os_mode, 1, "OS selector")
        else:
            codec.bounded(mode, 3, "submode")

        def operation():
            pages = []
            for page in range(8):
                command = (
                    codec.fn_read(profile, page, os_mode)
                    if fn
                    else codec.key_matrix_read(profile, page, mode, profile_max=1)
                )
                response = self.transport.exchange(command)
                if len(response) != 64:
                    raise ProtocolError("incomplete HE60 matrix page")
                pages.append(response)
            return b"".join(pages)

        return self.transport.transaction(operation)

    def set_key(self, slot, action, *, profile=0, fn=False, os_mode=0, mode=0):
        def operation():
            self._supported()
            codec.bounded(slot, 127, "slot")
            if fn:
                if profile != 0 or mode != 0:
                    raise ValueError("Fn writes use layer 0 and submode 0")
                codec.bounded(os_mode, 1, "OS selector")
            else:
                codec.bounded(mode, 3, "submode")
            command = (
                codec.fn_single(slot, action, layer=profile, os_mode=os_mode)
                if fn
                else codec.single_key(profile, slot, action, mode=mode, profile_max=1)
            )
            self._write([command])
            actual = self.read_matrix(profile, fn=fn, os_mode=os_mode, mode=mode)[
                slot * 4 : slot * 4 + 4
            ]
            if actual != bytes(action):
                raise ProtocolError("HE60 key readback differs")
            return list(actual)

        return self.transport.transaction(operation)

    def status(self):
        def operation():
            identity = self.identify()
            profile = self._query(codec.packet([0x84]), expected=0x84)[1]
            usb = identity["usb_version"] or None
            rf = None
            if self.expected_id == 3759:
                rf = parse_version("rf", self._query(version_request("rf"), expected=0x80))
            capabilities = [
                "keymap",
                "fn",
                "macro",
                "profile",
                "submodes",
                "os",
                "magnetic-read",
                "magnetic-actuation",
                "magnetic-modes",
            ]
            result = {
                "identity": self.identity,
                "model": self.model["displayName"],
                "profile": profile,
                "profiles": 2,
                "versions": {"usb": usb, "rf": rf},
                "capabilities": capabilities,
                "submodes": 4,
                "options": self.get_options(),
                "auto_os": self.get_auto_os(),
                "light": self.get_light(),
                "picture_banks": 3 if self.expected_id == 3727 else 5,
            }
            result["capabilities"].extend(("lighting", "picture"))
            if self.expected_id == 3727:
                result["capabilities"].append("debounce")
                result["debounce"] = self._query(codec.packet([0x86]), expected=0x86)[1]
            else:
                result["capabilities"].append("sleep")
                result["sleep"] = self.get_sleep()
            return result

        return self.transport.transaction(operation)

    def set_debounce(self, milliseconds):
        if self.expected_id != 3727:
            raise UnsupportedDevice("debounce is unavailable on wireless HE60 Lite")
        if type(milliseconds) is not int or not 1 <= milliseconds <= 10:
            raise ValueError("HE60 debounce must be an integer from 1 through 10")
        return super().set_debounce(milliseconds)

    def get_sleep(self):
        if self.expected_id != 3759:
            raise UnsupportedDevice("sleep controls are unavailable on wired HE60 Lite")
        raw = self._query(codec.packet([0x91]), expected=0x91)
        parsed = codec.parse_sleep(raw)
        parsed.pop("deep_dongle")
        return parsed

    def set_sleep(self, bt, dongle, deep_bt, deep_dongle=None):
        if self.expected_id != 3759:
            raise UnsupportedDevice("sleep controls are unavailable on wired HE60 Lite")
        if deep_dongle is not None:
            raise ValueError("wireless HE60 exposes three public sleep timers")
        values = (bt, dongle, deep_bt)
        if any(type(value) is not int or not 60 <= value <= 3600 for value in values):
            raise ValueError("HE60 sleep timers must be integers from 60 through 3600")

        def operation():
            original = self._query(codec.packet([0x91]), expected=0x91)
            command = bytearray(codec.sleep_times(bt, dongle, deep_bt, 0))
            command[14:16] = original[14:16]
            self._write([bytes(command)])
            actual = self._query(codec.packet([0x91]), expected=0x91)
            parsed = codec.parse_sleep(actual)
            if actual[14:16] != original[14:16]:
                raise ProtocolError("hidden sleep timer changed during write")
            if tuple(parsed[key] for key in ("bluetooth", "dongle", "deep_bluetooth")) != values:
                raise ProtocolError("sleep readback differs")
            parsed.pop("deep_dongle")
            return parsed

        return self.transport.transaction(operation)

    def get_magnetic(self):
        def operation():
            self.identify()
            before = self._query(codec.packet([0x84]), expected=0x84)[1]
            usb = self.identity["usb_version"] or None
            rf = (
                parse_version("rf", self._query(version_request("rf"), expected=0x80))
                if self.expected_id == 3759
                else None
            )
            multiplier = travel_multiplier(usb=usb, rf=rf)
            mode_data = self._read_field(7, 128)
            modes = list(mode_data)
            fields = {"7": mode_data.hex()}
            for field, length in ((0, 256), (1, 256), (6, 256)):
                fields[str(field)] = self._read_field(field, length).hex()
            if any(value & 0x80 for value in modes):
                for field in (2, 3):
                    fields[str(field)] = self._read_field(field, 256).hex()
            if any(value & 0x7F == 2 for value in modes):
                fields["4"] = self._read_field(4, 256).hex()
                fields["10"] = self._read_field(10, 512).hex()
            if any(value & 0x7F == 3 for value in modes):
                fields["5"] = self._read_field(5, 128).hex()
            if any(value & 0x7F == 7 for value in modes):
                fields["9"] = self._read_field(9, 128).hex()
            if top_dead_zone_supported(usb=usb, rf=rf):
                fields["251"] = self._read_field(251, 128).hex()
            after = self._query(codec.packet([0x84]), expected=0x84)[1]
            if after != before:
                raise ProtocolError("active profile changed during magnetic read")
            return {
                "profile": before,
                "versions": {"usb": usb, "rf": rf},
                "fields": fields,
                "modes": modes,
                "multiplier": multiplier,
                "slots": self._decode_slots(fields, modes, multiplier),
            }

        return self.transport.transaction(operation)

    @staticmethod
    def _decode_slots(fields, modes, multiplier):
        names = {0: "normal", 2: "dks", 3: "mt", 4: "tgl_hold", 5: "tgl_dots", 7: "snap"}
        raw = {int(field): bytes.fromhex(value) for field, value in fields.items()}
        slots = []
        for slot, mode_raw in enumerate(modes):
            mode = mode_raw & 0x7F
            item = {
                "slot": slot,
                "raw_mode": mode_raw,
                "mode": names.get(mode),
                "fire": bool(mode_raw & 0x80),
            }
            for field, name in (
                (0, "travel"),
                (1, "lift"),
                (2, "rapid_press"),
                (3, "rapid_lift"),
                (4, "dynamic"),
                (6, "deadzone"),
                (251, "top_deadzone"),
                (5, "mt_time"),
                (9, "bind_slot"),
            ):
                if str(field) in fields:
                    item[name] = decode_field(
                        field, key_field(raw[field], slot, field=field), multiplier=multiplier
                    )
            if "10" in fields:
                item["trigger_modes"] = [
                    key_field(raw[10], slot, field=10, stage=stage) for stage in range(4)
                ]
            slots.append(item)
        return slots

    def _read_field(self, field, length):
        pages = [
            self._query(encode_read(field, page))
            for page in range({128: 2, 256: 4, 512: 8}[length])
        ]
        return assemble_pages(pages, length=length)

    def set_magnetic_mode(self, slot, definition):
        """Install actions and magnetic parameters with full readback; not hardware atomic."""
        codec.bounded(slot, 127, "slot")
        definition = validate_definition(definition)

        def operation():
            state = self.get_magnetic()
            profile = state["profile"]
            for field, length in required_fields(definition, state["modes"][slot]).items():
                if str(field) not in state["fields"]:
                    state["fields"][str(field)] = self._read_field(field, length).hex()
            plan = plan_mode(self.expected_id, slot, definition, state)
            matrices = [self.read_matrix(profile, mode=submode) for submode in range(4)]
            expected_matrices = list(matrices)
            changed_actions = []
            for submode, action in enumerate(definition["actions"]):
                raw = bytearray(matrices[submode])
                raw[slot * 4 : slot * 4 + 4] = bytes.fromhex(action)
                expected_matrices[submode] = bytes(raw)
                if expected_matrices[submode] != matrices[submode]:
                    changed_actions.append(submode)
            commands = [
                codec.single_key(
                    profile,
                    slot,
                    bytes.fromhex(definition["actions"][submode]),
                    mode=submode,
                    profile_max=1,
                    commit=index == len(changed_actions) - 1,
                )
                for index, submode in enumerate(changed_actions)
            ] + plan["commands"]
            if self._query(codec.packet([0x84]), expected=0x84)[1] != profile:
                raise ProtocolError("active profile changed before magnetic mode write")
            if not commands:
                return {
                    "changed": False,
                    "profile": profile,
                    "mode": definition["mode"],
                    "slot": slot,
                }
            self._write(commands)
            actual_matrices = [self.read_matrix(profile, mode=submode) for submode in range(4)]
            actual_fields = {
                field: self._read_field(int(field), len(bytes.fromhex(value))).hex()
                for field, value in plan["expected_fields"].items()
            }
            if self._query(codec.packet([0x84]), expected=0x84)[1] != profile:
                raise ProtocolError(
                    "active profile changed during magnetic mode write; state may be partial"
                )
            if actual_matrices != expected_matrices:
                raise ProtocolError("magnetic action readback differs; state may be partial")
            if actual_fields != plan["expected_fields"]:
                raise ProtocolError("magnetic mode readback differs; state may be partial")
            return {"changed": True, "profile": profile, "mode": definition["mode"], "slot": slot}

        return self.transport.transaction(operation)

    def set_magnetic(self, slot, patch):
        """Patch actuation/rapid-trigger settings and verify complete read fields.

        The planner owns model limits and commit ordering. See
        docs/he60-lite-research.md; this does not switch the key's base mode.
        """
        codec.bounded(slot, 127, "slot")

        def operation():
            state = self.get_magnetic()
            # Read inactive RT values only when the patch needs them; ordinary
            # travel changes need not depend on an inactive field being readable.
            if isinstance(patch, dict) and (
                patch.get("fire") is True or "rapid_press" in patch or "rapid_lift" in patch
            ):
                for field in (2, 3):
                    if str(field) not in state["fields"]:
                        state["fields"][str(field)] = self._read_field(field, 256).hex()
            plan = plan_update(self.expected_id, slot, patch, state)
            before = self._query(codec.packet([0x84]), expected=0x84)[1]
            if before != state["profile"]:
                raise ProtocolError("active profile changed before magnetic write")
            if not plan["commands"]:
                return {"changed": False, "profile": before, "slot": state["slots"][slot]}
            self._write(plan["commands"])
            actual_fields = {
                field: self._read_field(int(field), len(bytes.fromhex(expected))).hex()
                for field, expected in plan["expected_fields"].items()
            }
            after = self._query(codec.packet([0x84]), expected=0x84)[1]
            if after != before:
                raise ProtocolError(
                    "active profile changed during magnetic write; state may be partial"
                )
            if actual_fields != plan["expected_fields"]:
                raise ProtocolError("magnetic readback differs; state may be partial")
            modes = list(bytes.fromhex(actual_fields["7"]))
            return {
                "changed": True,
                "profile": before,
                "slot": self._decode_slots(actual_fields, modes, state["multiplier"])[slot],
            }

        return self.transport.transaction(operation)
