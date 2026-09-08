"""RY5088 magnetic switch-type selection; vendor field 252 only."""

from __future__ import annotations

from . import codec
from .errors import ProtocolError, UnsupportedDevice
from .magnetic import encode_write
from .models import RY5088_SWITCH_IDS, model_by_id

SWITCH_TYPES = {
    "高特": 0,
    "磁玉": 1,
    "磁玉pro": 2,
    "磁玉gaming": 3,
    "天王": 4,
    "万磁王": 5,
    "冰玉": 33,
}


def resolve_switch(value):
    if type(value) is int and value in SWITCH_TYPES.values():
        return value
    if type(value) is str:
        if value in SWITCH_TYPES:
            return SWITCH_TYPES[value]
        if value.isascii() and value.isdecimal() and int(value) in SWITCH_TYPES.values():
            return int(value)
    raise ValueError("switch must be a supported vendor name or numeric code")


class HESwitchMixin:
    def set_switch_type(self, slots, switch):
        code = resolve_switch(switch)
        if not isinstance(slots, (list, tuple)) or not slots or len(slots) > 128:
            raise ValueError("slots must be a nonempty list or tuple of at most 128 slots")
        if any(type(slot) is not int or not 0 <= slot <= 127 for slot in slots):
            raise ValueError("slots must contain physical key slots from 0 through 127")
        if len(set(slots)) != len(slots):
            raise ValueError("slots must be unique")
        self._supported()
        if self.expected_id not in RY5088_SWITCH_IDS:
            raise UnsupportedDevice("this model does not support switch-type selection")
        supported = model_by_id(self.expected_id).get("other", {}).get("supportedSwitchTypes", [])
        if code not in {SWITCH_TYPES[name] for name in supported if name in SWITCH_TYPES}:
            raise ValueError("switch is not listed for this model")

        def operation():
            for slot in slots:
                self._snap_slot(slot)
            state = self.get_magnetic()
            profile = state["profile"]
            matrices = [self.read_matrix(profile, mode=mode) for mode in range(4)]
            axis = bytes.fromhex(state["fields"]["252"])
            expected_axis = bytearray(axis)
            changed = [slot for slot in slots if axis[slot] != code]
            if self._query(codec.packet([0x84]), expected=0x84)[1] != profile:
                raise ProtocolError("active profile changed before switch write")
            for slot in changed:
                expected_axis[slot] = code
                self._write([encode_write(252, slot, bytes((code,)), commit=True)])
            actual = self.get_magnetic()
            actual_matrices = [self.read_matrix(profile, mode=mode) for mode in range(4)]
            after_profile = self._query(codec.packet([0x84]), expected=0x84)[1]
            if after_profile != profile or actual["profile"] != profile:
                raise ProtocolError("active profile changed during switch write")
            if actual_matrices != matrices:
                raise ProtocolError("switch write changed key matrices")
            actual_axis = bytes.fromhex(actual["fields"]["252"])
            if actual_axis != bytes(expected_axis):
                raise ProtocolError("switch type readback differs")
            for field, value in state["fields"].items():
                if field != "252" and actual["fields"].get(field) != value:
                    raise ProtocolError("switch write changed magnetic fields")
            return {"changed": bool(changed), "profile": profile, "slots": slots, "axis_type": code}

        return self.transport.transaction(operation)
