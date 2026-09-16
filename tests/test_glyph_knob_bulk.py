"""Glyph bulk operations retain the three physical knob entries."""

import json

import pytest

from epomaker_driver import snapshot, vendor_apply
from epomaker_driver.device import Keyboard
from epomaker_driver.models import glyph_matrix

KNOBS = {"AudioVolumeDown": 109, "MediaPlayPause": 53, "AudioVolumeUp": 108}


def _record(fn: bool) -> dict:
    actions = []
    baseline = glyph_matrix()
    for slot, original in ((53, 0x0300CD00), (108, 0x0300E900), (109, 0x0300EA00)):
        assert baseline[slot * 4 : slot * 4 + 4] == original.to_bytes(4, "big")
    for original, macro_index in ((0x0300CD00, 7), (0x0300E900, 8), (0x0300EA00, 9)):
        actions.append(
            {
                "type": "ConfigMacro",
                "original": original,
                "macroType": "touch_repeat",
                "macroIndex": macro_index,
                "repeatCount": 1,
                "macro": [
                    {"type": "keyboard", "value": 5, "action": "down"},
                    {"type": "delay", "value": 10},
                ],
            }
        )
    return {
        "deviceType": {"id": 3059},
        "fn": fn,
        "value": actions,
    }


def _seed_knobs(firmware) -> dict[int, bytes]:
    values = {
        53: bytes.fromhex("09020700"),
        108: bytes.fromhex("09020800"),
        109: bytes.fromhex("09020900"),
    }
    for slot, value in values.items():
        for matrix in firmware.matrices:
            matrix[slot * 4 : slot * 4 + 4] = value
        firmware.fn[0][slot * 4 : slot * 4 + 4] = value
        firmware.fn[1][slot * 4 : slot * 4 + 4] = value
        firmware.macros[value[2]] = bytearray([1, 0, 5, 0x80 | value[2]] + [0] * 252)
    assert bytes(firmware.matrices[0][53 * 4 : 53 * 4 + 4]) == values[53]
    return values


@pytest.mark.parametrize("target", ["Main", "Fn Windows", "Fn Mac"])
def test_bulk_macro_apply_preserves_knobs_and_fn_layers(firmware, tmp_path, target):
    _seed_knobs(firmware)
    before = snapshot.capture(Keyboard(firmware))
    firmware.sent.clear()
    result = vendor_apply.apply(
        Keyboard(firmware), _record(target != "Main"), tmp_path / "recovery.json", target=target
    )
    assert result["imported"]
    after = snapshot.capture(Keyboard(firmware))
    selected = bytes.fromhex(
        after["matrices"][0]
        if target == "Main"
        else after["fn"]["win" if target == "Fn Windows" else "mac"]
    )
    for assignment in result["assignments"]:
        knob_slot = (53, 108, 109)[assignment["action_index"]]
        assert selected[knob_slot * 4 : knob_slot * 4 + 4] == bytes((9, 2, assignment["slot"], 0))
    if target == "Main":
        assert after["fn"] == before["fn"]
        assert after["matrices"][1:] == before["matrices"][1:]
    else:
        assert after["matrices"] == before["matrices"]
        other = "mac" if target == "Fn Windows" else "win"
        assert after["fn"][other] == before["fn"][other]
    assert json.loads((tmp_path / "recovery.json").read_text()) == before
    writes = [command[0] for command in firmware.sent]
    binding_op = 0x0A if target == "Main" else 0x10
    assert writes and max(i for i, op in enumerate(writes) if op == 0x0B) < writes.index(binding_op)
    assert all(
        bytes.fromhex(after["macros"][str(assignment["slot"])])
        == bytes.fromhex("0100058a" + "00" * 252)
        for assignment in result["assignments"]
    )


def test_snapshot_restore_preserves_knobs_across_profiles(firmware, tmp_path):
    values = _seed_knobs(firmware)
    keyboard = Keyboard(firmware)
    saved = snapshot.capture(keyboard)
    for matrix in firmware.matrices + firmware.fn:
        matrix[53 * 4 : 53 * 4 + 4] = bytes.fromhex("03000000")
        matrix[108 * 4 : 108 * 4 + 4] = bytes.fromhex("03000000")
        matrix[109 * 4 : 109 * 4 + 4] = bytes.fromhex("03000000")
    for macro_slot in (7, 8, 9):
        firmware.macros[macro_slot] = bytearray(256)
    mutated = snapshot.capture(keyboard)
    assert mutated["macros"] != saved["macros"]
    result = snapshot.restore(keyboard, saved, tmp_path / "restore-recovery.json")
    assert result["restored"]
    assert json.loads((tmp_path / "restore-recovery.json").read_text()) == mutated
    for matrix in firmware.matrices + firmware.fn:
        for slot, value in values.items():
            assert bytes(matrix[slot * 4 : slot * 4 + 4]) == value
    restored = snapshot.capture(keyboard)
    assert restored["matrices"] == saved["matrices"]
    assert restored["fn"] == saved["fn"]
    assert restored["macros"] == saved["macros"]
