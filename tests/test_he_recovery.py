import copy

import pytest
from he_snapshot_firmware import snapshot_keyboard

from epomaker_driver import he_recovery, he_snapshot, profiles
from epomaker_driver.errors import ProtocolError
from epomaker_driver.models import RY5088_IDS

MODELS = (*RY5088_IDS, 3727, 3759)


def change_every_domain(fw):
    for key in fw.matrices:
        fw.matrices[key] = bytes([0, 0, 4, 0]) * 128
    for key in fw.fn:
        fw.fn[key] = bytes([0, 0, 5, 0]) * 128
    for row in fw.profile_fields.values():
        for key, raw in row.items():
            row[key] = bytes(value ^ 1 for value in raw)
    fw.macros[255] = bytes(256)
    for bank in fw.pictures:
        fw.pictures[bank] = bytes([123]) * 378
    fw.light[5] ^= 1
    fw.side_light[5] ^= 1
    fw.options[3] ^= 1
    fw.sleep = [120, 180, 600, 42]
    fw.auto_os = True
    fw.debounce = 5


@pytest.mark.parametrize("model", MODELS)
def test_restore_all_profiles_and_domains_and_keep_recovery_copy(model, tmp_path):
    kb, fw = snapshot_keyboard(model)
    kb.set_profile(kb._profile_max())
    target = he_snapshot.capture(kb)
    change_every_domain(fw)
    kb.set_profile(0)
    before = he_snapshot.capture(kb)
    backup = tmp_path / "previous.json"
    result = he_recovery.restore(kb, target, backup)
    assert result["restored"]
    assert profiles.decode(backup.read_bytes()) == before
    he_recovery._compare(
        he_snapshot.validate(target), he_snapshot.validate(he_snapshot.capture(kb))
    )
    assert fw.profile == kb._profile_max()
    assert fw.macros[255] == bytes([255]) * 256
    assert backup.stat().st_mode & 0o777 == 0o600


def test_restore_rejects_model_mismatch_without_writes(tmp_path):
    source, _ = snapshot_keyboard(3692)
    target = he_snapshot.capture(source)
    kb, fw = snapshot_keyboard(2761)
    with pytest.raises(ValueError, match="model"):
        he_recovery.restore(kb, target, tmp_path / "backup")
    assert fw.sent == []


@pytest.mark.parametrize("model,component", [(3692, "rf_version"), (3727, "usb_version")])
def test_firmware_mismatch_never_writes_configuration(model, component, tmp_path):
    kb, fw = snapshot_keyboard(model)
    target = he_snapshot.capture(kb)
    setattr(fw, component, 0x0300)
    fw.sent.clear()
    with pytest.raises(ValueError, match="firmware"):
        he_recovery.restore(kb, target, tmp_path / "backup")
    assert all(command[0] == 4 for command in fw.sent)
    assert not (tmp_path / "backup").exists()


def test_existing_backup_prevents_restore_payload_writes(tmp_path):
    kb, fw = snapshot_keyboard()
    target = he_snapshot.capture(kb)
    change_every_domain(fw)
    path = tmp_path / "existing"
    path.write_text("keep")
    fw.sent.clear()
    with pytest.raises(FileExistsError):
        he_recovery.restore(kb, target, path)
    assert path.read_text() == "keep"
    assert all(command[0] == 4 for command in fw.sent)


@pytest.mark.parametrize("failure", ["magnetic", "action", "light", "sleep"])
def test_failed_restore_retains_backup_and_restores_original_profile(failure, tmp_path):
    kb, fw = snapshot_keyboard()
    target = he_snapshot.capture(kb)
    change_every_domain(fw)
    kb.set_profile(2)
    if failure == "magnetic":
        fw.drop_magnetic_write = True
    elif failure == "action":
        fw.drop_raw_setting = 0x0A
    elif failure == "light":
        fw.drop_raw_setting = 7
    else:
        fw.drop_sleep_write = True
    path = tmp_path / "recovery"
    with pytest.raises(ProtocolError, match="previous configuration is saved"):
        he_recovery.restore(kb, target, path)
    assert path.exists()
    assert fw.profile == 2
    he_snapshot.validate(profiles.decode(path.read_bytes()))


def test_invalid_snapshot_rejected_before_device_access(tmp_path):
    kb, _ = snapshot_keyboard()
    target = he_snapshot.capture(kb)
    bad = copy.deepcopy(target)
    bad["profiles"][0]["fields"]["0"] = "00"

    class Unopened:
        def identify(self):
            pytest.fail("must reject before I/O")

    with pytest.raises(ValueError):
        he_recovery.restore(Unopened(), bad, tmp_path / "backup")


def test_restore_old_firmware_without_top_deadzone(tmp_path):
    kb, fw = snapshot_keyboard(3727)
    fw.usb_version = 0x0200
    target = he_snapshot.capture(kb)
    assert "251" not in target["profiles"][0]["fields"]
    change_every_domain(fw)
    assert he_recovery.restore(kb, target, tmp_path / "old")["restored"]


@pytest.mark.parametrize("setting", ["options", "side_light"])
def test_raw_setting_readback_failure(setting, tmp_path):
    kb, fw = snapshot_keyboard(3703)
    target = he_snapshot.capture(kb)
    change_every_domain(fw)
    fw.drop_raw_setting = 9 if setting == "options" else 8
    with pytest.raises(ProtocolError, match=f"{setting} readback"):
        he_recovery.restore(kb, target, tmp_path / "recovery")


def test_cancellation_and_cleanup_failure_report_backup(tmp_path, monkeypatch):
    kb, fw = snapshot_keyboard()
    target = he_snapshot.capture(kb)
    change_every_domain(fw)
    original = kb.set_profile
    restoring = [False]

    def cancel(*_):
        restoring[0] = True
        raise KeyboardInterrupt("cancelled")

    def cannot_restore(profile):
        if restoring[0]:
            raise RuntimeError("disconnected")
        return original(profile)

    monkeypatch.setattr(kb, "write_macro", cancel)
    monkeypatch.setattr(kb, "set_profile", cannot_restore)
    path = tmp_path / "recovery"
    with pytest.raises(
        ProtocolError, match="KeyboardInterrupt.*original profile could not be restored"
    ):
        he_recovery.restore(kb, target, path)
    assert path.exists()


@pytest.mark.parametrize("key", ["macros", "light", "side_light", "sleep"])
def test_final_comparison_detects_late_changes(key):
    kb, _ = snapshot_keyboard(3703)
    target = he_snapshot.validate(he_snapshot.capture(kb))
    actual = copy.deepcopy(target)
    if key == "macros":
        actual[key][254] = bytes([1]) * 256
    else:
        data = bytearray(actual[key])
        data[8 if key == "sleep" else 5] ^= 1
        actual[key] = bytes(data)
    with pytest.raises(ProtocolError, match=f"final {key}"):
        he_recovery._compare(target, actual)


@pytest.mark.parametrize("failure", ["profile", "action"])
def test_magnetic_write_detects_profile_or_action_interference(failure, tmp_path, monkeypatch):
    kb, fw = snapshot_keyboard()
    target = he_snapshot.capture(kb)
    change_every_domain(fw)
    original = fw.send
    tripped = [False]

    def interfere(command):
        original(command)
        if command[0] == 0x65 and not tripped[0]:
            tripped[0] = True
            if failure == "profile":
                fw.profile = 1
                fw.fields = fw.profile_fields[1]
            else:
                fw.matrices[fw.profile, 3] = bytes([123]) * 512

    monkeypatch.setattr(fw, "send", interfere)
    with pytest.raises(ProtocolError, match="active profile|action matrix"):
        he_recovery.restore(kb, target, tmp_path / "recovery")
    assert tripped[0]


def test_recovery_also_preserves_firmware_with_global_magnetic_storage(tmp_path):
    kb, fw = snapshot_keyboard()
    shared = fw.profile_fields[0]
    fw.profile_fields = {p: shared for p in range(4)}
    fw.fields = shared
    target = he_snapshot.capture(kb)
    shared[0] = bytes([17]) * 256
    shared[252] = bytes([33]) * 128
    assert he_recovery.restore(kb, target, tmp_path / "global")["restored"]
    assert all(
        row["fields"] == target["profiles"][0]["fields"]
        for row in he_snapshot.capture(kb)["profiles"]
    )


def test_capture_rejects_same_pid_identity_change_mid_capture(monkeypatch):
    kb, fw = snapshot_keyboard(3692)
    original = kb.get_magnetic

    def change_identity():
        result = original()
        kb.expected_id = 2761
        return result

    monkeypatch.setattr(kb, "get_magnetic", change_identity)
    with pytest.raises(ProtocolError, match="identity or active profile"):
        he_snapshot.capture(kb)


def test_capture_rejects_profile_switch_during_global_reads(monkeypatch):
    kb, fw = snapshot_keyboard()
    original = kb.read_macro

    def late_switch(slot):
        result = original(slot)
        if slot == 255:
            fw.profile = 1
            fw.fields = fw.profile_fields[1]
        return result

    monkeypatch.setattr(kb, "read_macro", late_switch)
    with pytest.raises(ProtocolError, match="global configuration"):
        he_snapshot.capture(kb)
    assert fw.profile == 0


def test_mode_change_reapplies_even_previously_equal_parameters(tmp_path, monkeypatch):
    kb, fw = snapshot_keyboard()
    target = he_snapshot.capture(kb)
    for fields in fw.profile_fields.values():
        fields[7] = bytes([1]) * 128
    original = fw.send

    def mode_resets(command):
        original(command)
        if command[0] == 0x65 and command[1] == 7:
            slot = command[3]
            raw = bytearray(fw.fields[0])
            raw[slot * 2 : slot * 2 + 2] = bytes(2)
            fw.fields[0] = bytes(raw)
            axis = bytearray(fw.fields[252])
            axis[slot] = 0
            fw.fields[252] = bytes(axis)

    monkeypatch.setattr(fw, "send", mode_resets)
    assert he_recovery.restore(kb, target, tmp_path / "recovery")["restored"]
