"""HE60 reciprocal snap pairs; protocol evidence in docs/he60-lite-research.md."""

from . import codec
from .errors import ProtocolError
from .magnetic import encode_write
from .models import data_file


class HESnapMixin:
    def _snap_slot(self, slot):
        codec.bounded(slot, 127, "slot")
        default = bytes(data_file("he60-matrices.json")[str(self.expected_id)]["defaultMatrix"])
        action = default[slot * 4 : slot * 4 + 4]
        if not any(action) or action[:2] == bytes([10, 1]):
            raise ValueError("snap requires a physical non-Fn key")
        return action

    def set_snap(self, first, second):
        self._snap_slot(first)
        self._snap_slot(second)
        if first == second:
            raise ValueError("snap requires two different keys")
        return self.transport.transaction(lambda: self._snap_change(first, second))

    def clear_snap(self, slot):
        """Restore both ordinary bindings and remove snap modes; retain travel and rapid trigger."""
        self._snap_slot(slot)
        return self.transport.transaction(lambda: self._snap_change(slot, None))

    def _snap_change(self, first, second):
        state = self.get_magnetic()
        profile = state["profile"]
        modes = state["modes"]
        clearing = second is None
        if clearing and modes[first] & 0x7F != 7:
            if self._query(codec.packet([0x84]), expected=0x84)[1] != profile:
                raise ProtocolError("profile changed before snap operation")
            return {"changed": False, "profile": profile, "slots": [first]}
        if "9" not in state["fields"]:
            state["fields"]["9"] = self._read_field(9, 128).hex()
        links = bytes.fromhex(state["fields"]["9"])
        if clearing:
            second = links[first]
            self._snap_slot(second)
        selected = (first, second)
        paired = all(modes[slot] & 0x7F == 7 for slot in selected)
        reciprocal = first != second and links[first] == second and links[second] == first
        if clearing and not (paired and reciprocal):
            raise ValueError("snap pair is inconsistent; refusing to infer a repair")
        if any(
            modes[slot] & 0x7F == 7 and links[slot] in selected and slot not in selected
            for slot in range(128)
        ):
            raise ValueError("another snap key refers to this pair")
        if not clearing and not (paired and reciprocal):
            if any(modes[slot] & 0x7F not in (0, 2, 3, 4, 5) for slot in selected):
                raise ValueError("key is already paired or has an unknown magnetic mode")
        if not clearing and paired and reciprocal:
            if self._query(codec.packet([0x84]), expected=0x84)[1] != profile:
                raise ProtocolError("profile changed before snap operation")
            return {"changed": False, "profile": profile, "slots": list(selected)}
        matrices = [self.read_matrix(profile, mode=submode) for submode in range(4)]
        expected_matrices = [bytearray(matrix) for matrix in matrices]
        expected_fields = {
            field: bytearray.fromhex(value) for field, value in state["fields"].items()
        }
        commands = []
        for slot in selected:
            # Pair removal restores both keys; pairing restores advanced keys.
            if clearing or modes[slot] & 0x7F in (2, 3, 4, 5):
                actions = [self._snap_slot(slot), bytes(4), bytes(4), bytes(4)]
                changed = []
                for submode, action in enumerate(actions):
                    expected_matrices[submode][slot * 4 : slot * 4 + 4] = action
                    if matrices[submode][slot * 4 : slot * 4 + 4] != action:
                        changed.append(submode)
                commands.extend(
                    codec.single_key(
                        profile,
                        slot,
                        actions[submode],
                        mode=submode,
                        profile_max=1,
                        commit=index == len(changed) - 1,
                    )
                    for index, submode in enumerate(changed)
                )
        for index, slot in enumerate(selected):
            value = (modes[slot] & 0x80) | (0 if clearing else 7)
            expected_fields["7"][slot] = value
            commands.append(encode_write(7, slot, [value], commit=clearing and index == 1))
        if not clearing:
            for index, (slot, partner) in enumerate(((first, second), (second, first))):
                expected_fields["9"][slot] = partner
                commands.append(encode_write(9, slot, [partner], commit=index == 1))
        if self._query(codec.packet([0x84]), expected=0x84)[1] != profile:
            raise ProtocolError("profile changed before snap write")
        self._write(commands)
        actual_matrices = [self.read_matrix(profile, mode=submode) for submode in range(4)]
        actual_fields = {
            field: self._read_field(int(field), len(value))
            for field, value in expected_fields.items()
        }
        if self._query(codec.packet([0x84]), expected=0x84)[1] != profile:
            raise ProtocolError("profile changed during snap write; state may be partial")
        if actual_matrices != expected_matrices or actual_fields != expected_fields:
            raise ProtocolError("snap readback differs; state may be partial")
        return {
            "changed": True,
            "profile": profile,
            "slots": list(selected),
            "paired": not clearing,
        }
