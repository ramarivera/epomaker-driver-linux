import copy
import json

import pytest

from epomaker_driver import codec, snapshot
from epomaker_driver.device import Keyboard
from epomaker_driver.errors import ProtocolError


def test_capture_restore_and_recovery(firmware, tmp_path):
    keyboard = Keyboard(firmware)
    firmware.matrices[1][20:24] = bytes([9, 0, 7, 0])
    firmware.fn[1][24:28] = bytes([9, 1, 8, 0])
    firmware.macros[7] = bytearray([1] * 256)
    firmware.macros[8] = bytearray([2] * 256)
    desired = snapshot.capture(keyboard)
    assert set(desired["macros"]) == {"7", "8"}
    firmware.matrices[1][20:24] = bytes(4)
    firmware.fn[1][24:28] = bytes(4)
    firmware.macros[7] = bytearray([3] * 256)
    firmware.profile = 2
    firmware.debounce = 17
    firmware.auto_os = True
    firmware.options[1] = 1
    firmware.light = bytearray(codec.light("wave", rgb=0x123456))
    before = snapshot.capture(keyboard, extra_macro_slots=[7])
    backup = tmp_path / "recovery.json"
    result = snapshot.restore(keyboard, desired, backup)
    assert result["restored"]
    saved = json.loads(backup.read_text())
    assert saved["macros"]["7"] == bytes([3] * 256).hex()
    assert snapshot.capture(keyboard) == desired
    snapshot.restore(keyboard, saved, tmp_path / "second.json")
    actual = snapshot.capture(keyboard, extra_macro_slots=[7])
    # Recovery retains extra overwritten slots, even if not bound to a key.
    assert actual == before


@pytest.mark.parametrize(
    "change",
    [
        lambda v: v.update(schema_version=1),
        lambda v: v["identity"].update(device_id=1),
        lambda v: v.update(matrices=["00"]),
        lambda v: v.update(macros={"01": bytes(256).hex()}),
        lambda v: v.update(macros={"2": "00"}),
        lambda v: v["matrices"].__setitem__(0, (bytes([9, 0, 1, 0]) + bytes(508)).hex()),
        lambda v: v["light"].update(raw=[0] * 64),
        lambda v: v["sleep"].update(deep_bluetooth=0),
        lambda v: v.update(profile=3),
        lambda v: v.update(auto_os=1),
        lambda v: v.pop("fn"),
        lambda v: v.update(macros=[]),
    ],
)
def test_invalid_snapshot_never_writes(firmware, tmp_path, change):
    keyboard = Keyboard(firmware)
    value = copy.deepcopy(snapshot.capture(keyboard))
    change(value)
    with pytest.raises(ValueError):
        snapshot.restore(keyboard, value, tmp_path / "recovery.json")
    assert firmware.sent == []
    assert not (tmp_path / "recovery.json").exists()


def test_existing_recovery_file_prevents_writes(firmware, tmp_path):
    keyboard = Keyboard(firmware)
    value = snapshot.capture(keyboard)
    path = tmp_path / "exists.json"
    path.write_text("keep")
    with pytest.raises(FileExistsError):
        snapshot.restore(keyboard, value, path)
    assert path.read_text() == "keep"
    assert firmware.sent == []


@pytest.mark.parametrize("ignore", [7, 8, 9, 17])
def test_failed_restore_exposes_recovery_copy(firmware, tmp_path, ignore):
    keyboard = Keyboard(firmware)
    value = snapshot.capture(keyboard)
    firmware.light[3] = 1
    firmware.side_light[3] = 1
    firmware.options[1] = 1
    firmware.sleep_data = bytearray(codec.sleep_times(8, 9, 10, 11))
    send = firmware.send
    firmware.send = lambda p, **kw: None if p[0] == ignore else send(p, **kw)
    path = tmp_path / "recovery.json"
    with pytest.raises(ProtocolError, match="partially changed"):
        snapshot.restore(keyboard, value, path)
    assert json.loads(path.read_text())["light"]["brightness"] == 1


def test_short_macro_replacement_clears_old_tail(firmware):
    keyboard = Keyboard(firmware)
    firmware.macros[3] = bytearray([5] * 256)
    keyboard.write_macro(3, codec.macro_data(1, []))
    assert firmware.macros[3] == bytes([1]) + bytes(255)


def test_picture_snapshots_and_legacy_restore(firmware, tmp_path):
    keyboard = Keyboard(firmware)
    for index in range(5):
        firmware.pictures[index][:378] = bytes([index + 1] * 378)
    value = snapshot.capture(keyboard)
    assert value["schema_version"] == 3
    firmware.pictures[4][:378] = bytes(378)
    snapshot.restore(keyboard, value, tmp_path / "recovery.json")
    assert bytes(firmware.pictures[4][:378]) == bytes([5] * 378)
    legacy = copy.deepcopy(value)
    legacy["schema_version"] = 2
    del legacy["pictures"]
    firmware.pictures[0][:378] = bytes([7] * 378)
    result = snapshot.restore(keyboard, legacy, tmp_path / "legacy-recovery.json")
    assert "unchanged" in result["limitations"][-1]
    assert bytes(firmware.pictures[0][:378]) == bytes([7] * 378)
    for invalid in ([], [bytes(377).hex()] * 5):
        bad = copy.deepcopy(value)
        bad["pictures"] = invalid
        before = list(firmware.sent)
        with pytest.raises(ValueError, match="five 378-byte"):
            snapshot.restore(keyboard, bad, tmp_path / "invalid.json")
        assert firmware.sent == before
