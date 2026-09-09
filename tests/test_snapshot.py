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
    assert set(desired["macros"]) == {str(slot) for slot in range(256)}
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
        lambda v: (
            v["matrices"].__setitem__(0, (bytes([9, 0, 1, 0]) + bytes(508)).hex()),
            v["macros"].pop("1"),
        ),
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


def test_factory_reset_preserves_unreferenced_macros_before_reset(firmware, tmp_path):
    keyboard = Keyboard(firmware)
    firmware.macros[255] = bytearray([17] * 256)
    destination = tmp_path / "before-reset.json"
    sent = firmware.send
    sleeps = []
    firmware.sleep = sleeps.append

    def send(command, **options):
        import json

        value = json.loads(destination.read_text())
        assert len(value["macros"]) == 256
        assert value["macros"]["255"] == bytes([17] * 256).hex()
        sent(command, **options)

    firmware.send = send
    result = snapshot.factory_reset(keyboard, destination)
    assert firmware.sent == [bytes.fromhex("01000000000000fe") + bytes(56)]
    assert sleeps == [2]
    assert result["reset_sent"] and not result["factory_defaults_verified"]
    assert keyboard.identity is None and keyboard.model is None
    with pytest.raises(FileExistsError):
        snapshot.factory_reset(keyboard, destination)
    assert len(firmware.sent) == 1


def test_factory_reset_failure_keeps_recovery_and_invalidates_identity(firmware, tmp_path):
    keyboard = Keyboard(firmware)
    destination = tmp_path / "before-reset.json"

    def fail(*args, **kwargs):
        raise OSError("disconnected")

    firmware.send = fail
    with pytest.raises(ProtocolError, match="reset outcome is unknown"):
        snapshot.factory_reset(keyboard, destination)
    assert destination.exists()
    assert keyboard.identity is None
    firmware.sent.clear()
    destination = tmp_path / "missing-backup.json"
    firmware.exchange = fail
    with pytest.raises(OSError, match="disconnected"):
        snapshot.factory_reset(keyboard, destination)
    assert not destination.exists()
    assert not firmware.sent


def rt85_keyboard(firmware):
    from epomaker_driver.models import default_matrix

    firmware.model_id = 2895
    firmware.matrices = [bytearray(default_matrix(2895)) for _ in range(4)]
    firmware.fn = [
        bytearray(default_matrix(2895, name)) for name in ("defaultFnMatrix", "defaultFnMacMatrix")
    ]
    return Keyboard(firmware)


def test_rt85_full_recovery_roundtrip(firmware, tmp_path):
    keyboard = rt85_keyboard(firmware)
    keyboard.set_profile(3)
    keyboard.write_macro(255, bytes([123]) * 256)
    keyboard.set_key(9, [9, 0, 255, 0], profile=3)
    keyboard.set_light("wave", side=True, speed=4)
    original = snapshot.capture(keyboard)
    assert original["schema_version"] == 4 and original["debounce"] is None
    assert len(original["matrices"]) == 4 and "255" in original["macros"]
    keyboard.write_matrix(bytes(512), 3)
    keyboard.set_profile(1)
    keyboard.set_light("solid", side=True)
    current = snapshot.capture(keyboard)
    firmware.sent.clear()
    destination = tmp_path / "recovery.json"
    result = snapshot.restore(keyboard, original, destination)
    assert result["restored"]
    assert snapshot.capture(keyboard) == original
    assert json.loads(destination.read_text())["matrices"] == current["matrices"]
    assert all(p[0] != 6 for p in firmware.sent)  # no unmigrated debounce write
    with pytest.raises(FileExistsError):
        snapshot.restore(keyboard, original, destination)


@pytest.mark.parametrize("source,target", [(2895, 3059), (3059, 2895)])
def test_cross_model_restore_stops_before_backup_or_writes(firmware, tmp_path, source, target):
    keyboard = rt85_keyboard(firmware) if source == 2895 else Keyboard(firmware)
    value = snapshot.capture(keyboard)
    firmware.model_id = target
    firmware.sent.clear()
    destination = tmp_path / "recovery.json"
    with pytest.raises(ValueError, match="does not match"):
        snapshot.restore(keyboard, value, destination)
    assert not destination.exists() and not firmware.sent


@pytest.mark.parametrize(
    "damage",
    [
        lambda v: v.update(schema_version=3),
        lambda v: v["matrices"].pop(),
        lambda v: v.update(profile=4),
        lambda v: v.update(debounce=5),
        lambda v: v["side_light"]["raw"].__setitem__(1, 5),
        lambda v: v["side_light"]["raw"].__setitem__(2, 4),
        lambda v: v["identity"].__setitem__("device_id", 2895.0),
    ],
)
def test_rt85_invalid_snapshot_never_writes(firmware, tmp_path, damage):
    keyboard = rt85_keyboard(firmware)
    value = snapshot.capture(keyboard)
    damage(value)
    with pytest.raises(ValueError):
        snapshot.restore(keyboard, value, tmp_path / "bad.json")
    assert not firmware.sent
    assert not (tmp_path / "bad.json").exists()


def test_rt85_factory_reset_saves_all_profiles_macros(firmware, tmp_path):
    keyboard = rt85_keyboard(firmware)
    firmware.macros[255] = bytearray([42] * 256)
    firmware.matrices[3][36:40] = bytes([0, 0, 5, 0])
    destination = tmp_path / "reset.json"
    send = firmware.send

    def reset(command, **kwargs):
        if command[0] == 1:
            saved = json.loads(destination.read_text())
            assert len(saved["matrices"]) == 4
            assert len(saved["macros"]) == 256
            assert saved["macros"]["255"] == bytes([42] * 256).hex()
            assert saved["debounce"] is None
        send(command, **kwargs)

    firmware.send = reset
    result = snapshot.factory_reset(keyboard, destination)
    assert result["reset_sent"] and not result["factory_defaults_verified"]
    assert firmware.sent == [codec.packet([1])]
    assert keyboard.identity is None


def test_rt85_bad_recovery_state_prevents_reset(firmware, tmp_path):
    keyboard = rt85_keyboard(firmware)
    firmware.side_light[1] = 5  # not a supported RT85 side mode
    path = tmp_path / "reset.json"
    with pytest.raises(ValueError, match="side lighting"):
        snapshot.factory_reset(keyboard, path)
    assert not path.exists() and not firmware.sent


def test_glyph_version4_import(firmware, tmp_path):
    keyboard = Keyboard(firmware)
    value = snapshot.capture(keyboard)
    value["schema_version"] = 4
    assert snapshot.restore(keyboard, value, tmp_path / "glyph.json")["restored"]


def rt75_keyboard(firmware):
    from epomaker_driver.models import default_matrix

    firmware.model_id = 3223
    firmware.matrices = [bytearray(default_matrix(3223)) for _ in range(3)]
    firmware.fn = [
        bytearray(default_matrix(3223, name)) for name in ("defaultFnMatrix", "defaultFnMacMatrix")
    ]
    firmware.sleep_data = bytearray(codec.sleep_times(60, 120, 600, 1200))
    return Keyboard(firmware)


def test_rt75_snapshot_restores_actual_mac_fn_without_side_light(firmware, tmp_path):
    keyboard = rt75_keyboard(firmware)
    keyboard.set_key(9, [0, 0, 6, 0], fn=True, os_mode=1)
    original = snapshot.capture(keyboard)
    assert original["schema_version"] == 4 and original["side_light"] is None
    keyboard.set_key(9, [0, 0, 7, 0], fn=True, os_mode=1)
    keyboard.set_debounce(20)
    keyboard.set_sleep(120, 240, 1200, 1800)
    firmware.sent.clear()
    result = snapshot.restore(keyboard, original, tmp_path / "recovery.json")
    assert result["restored"]
    assert snapshot.capture(keyboard) == original
    assert all(p[0] != 8 for p in firmware.sent)
    assert keyboard.read_matrix(fn=True, os_mode=1)[36:40] == bytes([0, 0, 6, 0])


@pytest.mark.parametrize(
    "damage",
    [
        lambda v: v.update(side_light={"raw": list(codec.packet([0x88]))}),
        lambda v: v["sleep"].update(bluetooth=0),
        lambda v: v["sleep"].update(deep_dongle=3601),
        lambda v: v.update(debounce=None),
        lambda v: v.update(schema_version=3),
    ],
)
def test_rt75_bad_snapshots_fail_before_recovery_or_writes(firmware, tmp_path, damage):
    keyboard = rt75_keyboard(firmware)
    value = snapshot.capture(keyboard)
    damage(value)
    with pytest.raises(ValueError):
        snapshot.restore(keyboard, value, tmp_path / "recovery.json")
    assert not firmware.sent and not (tmp_path / "recovery.json").exists()


def test_rt75_factory_reset_validates_recovery(firmware, tmp_path):
    keyboard = rt75_keyboard(firmware)
    firmware.macros[255] = bytearray([123] * 256)
    destination = tmp_path / "reset.json"
    send = firmware.send

    def checked(command, **kwargs):
        saved = json.loads(destination.read_text())
        assert saved["side_light"] is None and len(saved["macros"]) == 256
        assert saved["macros"]["255"] == bytes([123] * 256).hex()
        send(command, **kwargs)

    firmware.send = checked
    assert snapshot.factory_reset(keyboard, destination)["reset_sent"]
    assert firmware.sent == [codec.packet([1])]
    assert keyboard.identity is None
    firmware.sleep_data = bytearray(codec.sleep_times(0, 0, 10, 10))
    firmware.sent.clear()
    with pytest.raises(ValueError):
        snapshot.factory_reset(keyboard, tmp_path / "invalid.json")
    assert not firmware.sent and not (tmp_path / "invalid.json").exists()


@pytest.mark.parametrize("source,target", [(3223, 3059), (3223, 2895), (3059, 3223), (2895, 3223)])
def test_rt75_cross_model_rejection(firmware, tmp_path, source, target):
    keyboard = {3223: rt75_keyboard, 2895: rt85_keyboard, 3059: Keyboard}[source](firmware)
    value = snapshot.capture(keyboard)
    firmware.model_id = target
    with pytest.raises(ValueError, match="does not match"):
        snapshot.restore(keyboard, value, tmp_path / "recovery.json")
    assert not firmware.sent and not (tmp_path / "recovery.json").exists()
