import copy
import json

import pytest

from epomaker_driver import snapshot
from epomaker_driver.device import Keyboard
from epomaker_driver.errors import ProtocolError


def test_glyph_capture_reads_all_macro_slots_and_updates_limitations(firmware):
    keyboard = Keyboard(firmware)
    firmware.macros[255] = bytearray([0xA5] * 256)
    value = snapshot.capture(keyboard)
    assert len(value["macros"]) == 256
    assert value["macros"]["255"] == bytes([0xA5] * 256).hex()
    assert all("unreferenced" not in item for item in value["limitations"])


def test_glyph_restore_partial_schema_does_not_clear_unmentioned_slots(firmware, tmp_path):
    keyboard = Keyboard(firmware)
    firmware.matrices[0][20:24] = bytes([9, 0, 7, 0])
    firmware.macros[7] = bytearray([7] * 256)
    firmware.macros[255] = bytearray([0xFF] * 256)
    value = snapshot.capture(keyboard)
    partial = copy.deepcopy(value)
    partial["macros"] = {"7": bytes(256).hex()}
    destination = tmp_path / "recovery.json"
    result = snapshot.restore(keyboard, partial, destination)
    assert result["restored"]
    assert firmware.macros[7] == bytes(256)
    assert firmware.macros[255] == bytes([0xFF] * 256)
    saved = json.loads(destination.read_text())
    assert len(saved["macros"]) == 256


def test_glyph_failed_macro_read_leaves_no_recovery_artifact(firmware, tmp_path, monkeypatch):
    keyboard = Keyboard(firmware)
    value = snapshot.capture(keyboard)
    original = keyboard.read_macro

    def fail(slot):
        if slot == 12:
            raise ProtocolError("macro read failed")
        return original(slot)

    monkeypatch.setattr(keyboard, "read_macro", fail)
    with pytest.raises(ProtocolError, match="macro read failed"):
        snapshot.restore(keyboard, value, tmp_path / "recovery.json")
    assert not (tmp_path / "recovery.json").exists()


def test_invalid_extra_macro_slot_fails_before_transaction(firmware, tmp_path):
    keyboard = Keyboard(firmware)
    before = list(firmware.sent)
    with pytest.raises(ValueError, match="extra macro slots"):
        snapshot.capture(keyboard, extra_macro_slots=[256])
    assert firmware.sent == before


def test_complete_backup_restores_unreferenced_and_empty_slots(firmware, tmp_path):
    keyboard = Keyboard(firmware)
    firmware.macros[255] = bytearray([0xA5] * 256)
    saved = snapshot.capture(keyboard)
    assert saved["macros"]["254"] == bytes(256).hex()
    firmware.macros[255] = bytearray(256)
    firmware.macros[254] = bytearray([0xB6] * 256)
    snapshot.restore(keyboard, saved, tmp_path / "before.json")
    assert firmware.macros[255] == bytes([0xA5] * 256)
    assert firmware.macros[254] == bytes(256)
    before = json.loads((tmp_path / "before.json").read_text())
    assert before["macros"]["254"] == bytes([0xB6] * 256).hex()
