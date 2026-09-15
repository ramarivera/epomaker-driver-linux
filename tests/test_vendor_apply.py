import json

import pytest

from epomaker_driver import snapshot, vendor_apply
from epomaker_driver.device import Keyboard
from epomaker_driver.errors import ProtocolError, UnsupportedDevice


def record(fn=False):
    return {
        "deviceType": {"id": 3059},
        "fn": fn,
        "value": [
            {
                "type": "ConfigMacro",
                "original": 4,
                "macroType": "on_off",
                "repeatCount": 1,
                "macro": [
                    {"type": "keyboard", "value": 5, "action": "down"},
                    {"type": "delay", "value": 10},
                ],
            },
        ],
    }


@pytest.mark.parametrize("target", ["Main", "Fn Windows", "Fn Mac"])
def test_import_preserves_other_layers_and_backs_up_all_macros(firmware, tmp_path, target):
    keyboard = Keyboard(firmware)
    firmware.matrices[2][0:4] = bytes([9, 1, 0, 0])
    firmware.macros[0] = bytearray([7] * 256)
    before = snapshot.capture(keyboard)
    backup = tmp_path / "before.json"
    result = vendor_apply.apply(keyboard, record(target != "Main"), backup, target=target)
    assert result["imported"]
    assert result["assignments"][0]["slot"] == 1
    assert json.loads(backup.read_text()) == before
    after = snapshot.capture(keyboard)
    assert after["macros"]["0"] == before["macros"]["0"]
    assert after["macros"]["1"] == "0100058a" + "00" * 252
    for index in range(3):
        if target != "Main" or index != 0:
            assert after["matrices"][index] == before["matrices"][index]
    for name in ("win", "mac"):
        if target != {"win": "Fn Windows", "mac": "Fn Mac"}[name]:
            assert after["fn"][name] == before["fn"][name]
    assert set(command[0] for command in firmware.sent) <= {0x0A, 0x0B, 0x10}


def test_existing_backup_prevents_any_write(firmware, tmp_path):
    backup = tmp_path / "existing.json"
    backup.write_text("keep")
    with pytest.raises(FileExistsError):
        vendor_apply.apply(Keyboard(firmware), record(), backup)
    assert not firmware.sent
    assert backup.read_text() == "keep"


def test_invalid_record_prevents_backup_and_writes(firmware, tmp_path):
    backup = tmp_path / "before.json"
    with pytest.raises(ValueError):
        vendor_apply.apply(Keyboard(firmware), {"deviceType": {"id": 1}}, backup)
    assert not firmware.sent
    assert not backup.exists()


def test_wrong_device_prevents_backup_and_writes(firmware, tmp_path):
    firmware.model_id = 2895
    with pytest.raises(UnsupportedDevice, match="Glyph only"):
        vendor_apply.apply(Keyboard(firmware), record(), tmp_path / "before.json")
    assert not firmware.sent


def test_failed_macro_write_leaves_binding_unchanged_and_recovery(firmware, tmp_path, monkeypatch):
    keyboard = Keyboard(firmware)
    before = bytes(firmware.matrices[0])
    backup = tmp_path / "before.json"

    def fail(*args):
        raise ProtocolError("macro readback differs")

    monkeypatch.setattr(keyboard, "write_macro", fail)
    with pytest.raises(ProtocolError, match="partially changed.*before.json"):
        vendor_apply.apply(keyboard, record(), backup)
    assert bytes(firmware.matrices[0]) == before
    assert len(json.loads(backup.read_text())["macros"]) == 256


def test_macro_verification_precedes_binding_write(firmware, tmp_path, monkeypatch):
    keyboard = Keyboard(firmware)
    original_read = keyboard.read_macro
    reads_after_write = []

    def read(slot):
        if firmware.sent:
            reads_after_write.append(slot)
            assert all(command[0] == 0x0B for command in firmware.sent)
        return original_read(slot)

    monkeypatch.setattr(keyboard, "read_macro", read)
    vendor_apply.apply(keyboard, record(), tmp_path / "before.json")
    assert reads_after_write == [0]
    assert firmware.sent[-1][0] == 0x0A


def test_matrix_failure_reports_saved_recovery(firmware, tmp_path, monkeypatch):
    keyboard = Keyboard(firmware)
    backup = tmp_path / "before.json"

    def fail(*args):
        raise ProtocolError("matrix readback differs")

    monkeypatch.setattr(keyboard, "write_matrix", fail)
    with pytest.raises(ProtocolError, match="partially changed.*matrix readback"):
        vendor_apply.apply(keyboard, record(), backup)
    saved = json.loads(backup.read_text())
    assert saved["macros"]["0"] == "00" * 256
    assert firmware.macros[0] == bytes.fromhex("0100058a" + "00" * 252)
