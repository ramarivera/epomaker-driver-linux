"""Schema-8 CH585 snapshot validation and capture tests."""

from __future__ import annotations

import copy

import pytest
from test_mouse import USB
from test_mouse_recovery_cli import BankedSettingsFirmware

from epomaker_driver import mouse_snapshot
from epomaker_driver.errors import ProtocolError, UnsupportedDevice
from epomaker_driver.mouse import Mouse
from epomaker_driver.transport import Transport


class _Transport:
    kind = "usb"

    def transaction(self, operation):
        return operation()


class FakeMouse:
    def __init__(self, model_id=3961, usb_version=0x0400):
        self.transport = _Transport()
        self.model_id = model_id
        self.usb_version = usb_version
        self.profile = 0
        self.fail_cleanup = False
        self.fail_capture = False
        self.matrices = {p: bytes([p]) * 64 for p in range(8)}
        self.dpis = {}
        for p in range(8):
            raw = bytearray(64)
            raw[:4] = bytes((0x90, p, 1, 6))
            raw[8:10] = (800).to_bytes(2, "little")
            raw[24:26] = (800).to_bytes(2, "little")
            self.dpis[p] = bytes(raw)
        self.macros = {slot: bytes([slot]) * 256 for slot in range(50)}
        self.settings = {
            p: {
                name: (False if name in ("line_repair", "wave_repair") else 0)
                for name in mouse_snapshot._setting_names(model_id, usb_version)
            }
            for p in range(8)
        }

    def identify(self):
        return {"device_id": self.model_id, "usb_version": self.usb_version}

    def _setting_supported(self, name):
        return None

    def get_profile(self):
        return self.profile

    def set_profile(self, profile):
        if profile == 0 and self.fail_cleanup:
            raise RuntimeError("profile cleanup failure")
        self.profile = profile

    def read_matrix(self, profile):
        if self.fail_capture and profile == 2:
            raise RuntimeError("primary capture failure")
        return self.matrices[profile]

    def get_dpi(self, profile):
        return {"raw": list(self.dpis[profile])}

    def get_setting(self, name):
        return self.settings[self.profile][name]

    def _query(self, payload, expected=None):
        raw = bytearray(64)
        raw[0] = 0x88
        raw[1] = 1
        return bytes(raw)

    def read_macro(self, slot):
        return self.macros[slot]


def snapshot_template(model_id=3961, usb_version=0x0400):
    names = mouse_snapshot._known_settings(model_id, usb_version)
    settings = {name: (False if name in ("line_repair", "wave_repair") else 0) for name in names}
    rows = [
        {
            "matrix": (bytes([p]) * 64).hex(),
            "dpi": (bytes([0x90, p, 1, 6]) + bytes(60)).hex(),
            "settings": dict(settings),
        }
        for p in range(8)
    ]
    return {
        "schema_version": 8,
        "identity": {"device_id": model_id, "usb_version": usb_version},
        "profile": 0,
        "profiles": rows,
        "macros": {str(slot): (bytes([slot]) * 256).hex() for slot in range(50)},
        "limitations": ["test"],
    }


def test_validate_decodes_strict_schema_and_raw_ui_out_of_range_values():
    value = snapshot_template()
    for row in value["profiles"]:
        row["settings"]["debounce"] = 255
    decoded = mouse_snapshot.validate(value)
    assert decoded["profiles"][0]["settings"]["debounce"] == 255
    assert decoded["profiles"][0]["settings"]["report_rate"] == 0


def test_capture_returns_json_snapshot_and_restores_original_profile():
    mouse = FakeMouse()
    mouse.profile = 3
    result = mouse_snapshot.capture(mouse)
    assert result["schema_version"] == 8
    assert isinstance(result["profiles"][0]["matrix"], str)
    assert set(result["macros"]) == {str(slot) for slot in range(50)}
    assert mouse.profile == 3


@pytest.mark.parametrize("field", ["identity", "profiles", "macros", "limitations"])
def test_validate_rejects_missing_required_fields(field):
    value = snapshot_template()
    del value[field]
    with pytest.raises(ValueError):
        mouse_snapshot.validate(value)


def test_validate_rejects_wrong_dpi_opcode_and_noncanonical_macro_key():
    value = snapshot_template()
    value["profiles"][0]["dpi"] = (bytes(64)).hex()
    with pytest.raises(ValueError, match="DPI"):
        mouse_snapshot.validate(value)
    value = snapshot_template()
    value["macros"]["01"] = value["macros"].pop("0")
    with pytest.raises(ValueError):
        mouse_snapshot.validate(value)


def test_validate_rejects_unknown_settings_and_wrong_profile_count():
    value = snapshot_template()
    value["profiles"][0]["settings"]["unknown"] = 1
    with pytest.raises(ValueError):
        mouse_snapshot.validate(value)
    value = snapshot_template()
    value["profiles"].pop()
    with pytest.raises(ValueError):
        mouse_snapshot.validate(value)


def test_raw_commands_clear_response_status_bytes_and_preserve_dpi_payload():
    raw = bytearray(64)
    raw[:4] = bytes((0x90, 2, 3, 6))
    raw[4:8] = bytes.fromhex("aabbccdd")
    raw[20] = 0x55
    command = mouse_snapshot._raw_dpi_command(bytes(raw), 4)
    assert command[0:4] == bytes((0x10, 4, 3, 6))
    assert command[4:7] == bytes(3)
    assert command[20] == 0x55
    assert command[7] == (255 - sum(command[:7])) & 255


def real_mouse(model=3961):
    firmware = BankedSettingsFirmware(model)
    mouse = Mouse(
        Transport(USB(firmware), "usb", sleep=lambda _: None), product_id=firmware.product_id
    )
    return mouse, firmware


def test_validate_rejects_malformed_types_and_wire_shapes():
    base = snapshot_template()
    mutations = []
    value = copy.deepcopy(base)
    value["schema_version"] = True
    mutations.append(value)
    value = copy.deepcopy(base)
    value["identity"] = None
    mutations.append(value)
    value = copy.deepcopy(base)
    value["profiles"][0]["matrix"] = "zz"
    mutations.append(value)
    value = copy.deepcopy(base)
    value["profiles"][0]["dpi"] = "00" * 64
    mutations.append(value)
    value = copy.deepcopy(base)
    value["macros"]["0"] = "00"
    mutations.append(value)
    value = copy.deepcopy(base)
    value["limitations"] = ["ok", 1]
    mutations.append(value)
    for invalid in mutations:
        with pytest.raises(ValueError):
            mouse_snapshot.validate(invalid)


def test_validate_rejects_boolean_or_overwide_identity_and_settings():
    value = snapshot_template()
    value["identity"]["usb_version"] = True
    with pytest.raises(ValueError):
        mouse_snapshot.validate(value)
    value = snapshot_template()
    value["profiles"][0]["settings"]["report_rate"] = 256
    with pytest.raises(ValueError):
        mouse_snapshot.validate(value)
    value = snapshot_template()
    value["profiles"][0]["settings"]["sleep_24"] = 65536
    with pytest.raises(ValueError):
        mouse_snapshot.validate(value)


def test_capture_reports_profile_cleanup_failure_without_primary_error():
    mouse = FakeMouse()
    mouse.fail_cleanup = True
    with pytest.raises(ProtocolError, match="cleanup failed"):
        mouse_snapshot.capture(mouse)


def test_capture_reports_primary_and_cleanup_failures_together():
    mouse = FakeMouse()
    mouse.fail_capture = True
    mouse.fail_cleanup = True
    with pytest.raises(ProtocolError, match="primary capture failure.*cleanup failed"):
        mouse_snapshot.capture(mouse)


def test_restore_rejects_exact_usb_version_mismatch_before_backup_or_write(tmp_path):
    mouse, firmware = real_mouse()
    snapshot = mouse_snapshot.capture(mouse)
    firmware.sent.clear()
    snapshot["identity"]["usb_version"] += 1
    backup = tmp_path / "before.json"
    with pytest.raises(ValueError, match="USB version"):
        mouse_snapshot.restore(mouse, snapshot, backup)
    assert not backup.exists()
    assert not firmware.sent


def test_restore_existing_backup_does_not_clobber_or_write(tmp_path):
    mouse, firmware = real_mouse()
    snapshot = mouse_snapshot.capture(mouse)
    firmware.sent.clear()
    backup = tmp_path / "before.json"
    backup.write_text("keep")
    with pytest.raises(FileExistsError):
        mouse_snapshot.restore(mouse, snapshot, backup)
    assert backup.read_text() == "keep"
    assert all(command[0] == 2 for command in firmware.sent)


def test_restore_partial_failure_saves_backup_and_restores_original_profile(monkeypatch, tmp_path):
    mouse, firmware = real_mouse()
    firmware.profile = 6
    snapshot = mouse_snapshot.capture(mouse)
    original = mouse.get_profile()

    def fail_after_profile(profile, data):
        firmware.profile = 2
        raise RuntimeError("injected matrix failure")

    monkeypatch.setattr(mouse, "write_matrix", fail_after_profile)
    backup = tmp_path / "before.json"
    with pytest.raises(ProtocolError, match="backup saved at .*before.json; partial state"):
        mouse_snapshot.restore(mouse, snapshot, backup)
    assert backup.exists()
    assert firmware.profile == original


def test_factory_reset_sends_exact_command_after_noclobber_backup(tmp_path):
    mouse, firmware = real_mouse()
    sleeps = []
    commands = []
    mouse.transport.sleep = sleeps.append
    original_send = mouse.transport.send

    def send(command, **kwargs):
        commands.append(bytes(command))
        if command[0] != 0x0E:
            original_send(command, **kwargs)

    mouse.transport.send = send
    result = mouse_snapshot.factory_reset(mouse, tmp_path / "before.json")
    assert result["reset_command_sent"] is True
    assert result["factory_defaults_verified"] is False
    reset_commands = [command for command in commands if command[0] == 0x0E]
    assert len(reset_commands) == 1
    assert reset_commands[0][7] == (255 - sum(reset_commands[0][:7])) & 255
    assert 0.3 in sleeps
    assert mouse.identity is not None


def test_factory_reset_existing_backup_fails_before_reset_packet(tmp_path):
    mouse, firmware = real_mouse()
    backup = tmp_path / "before.json"
    backup.write_text("keep")
    with pytest.raises(FileExistsError):
        mouse_snapshot.factory_reset(mouse, backup)
    assert backup.read_text() == "keep"
    assert not any(command[0] == 0x0E for command in firmware.sent)


def test_factory_reset_post_reset_identity_failure_reports_backup(tmp_path, monkeypatch):
    mouse, firmware = real_mouse()
    backup = tmp_path / "before.json"
    original_send = mouse.transport.send

    def send(command, **kwargs):
        if command[0] == 0x0E:
            firmware.model_id = 3303
            return
        original_send(command, **kwargs)

    monkeypatch.setattr(mouse.transport, "send", send)
    with pytest.raises(ProtocolError, match="post-reset verification failed"):
        mouse_snapshot.factory_reset(mouse, backup)
    assert backup.exists()


@pytest.mark.parametrize("failure", [OSError("lost connection"), KeyboardInterrupt()])
def test_factory_reset_interruption_invalidates_cache_and_reports_unknown_outcome(
    monkeypatch, tmp_path, failure
):
    mouse, firmware = real_mouse()
    original = mouse.transport.send

    def fail(command, **kwargs):
        if command[0] == 14:
            raise failure
        return original(command, **kwargs)

    monkeypatch.setattr(mouse.transport, "send", fail)
    backup = tmp_path / "before.json"
    with pytest.raises(ProtocolError, match="outcome is unknown.*before.json") as caught:
        mouse_snapshot.factory_reset(mouse, backup)
    assert backup.exists()
    assert caught.value.__cause__ is failure
    assert mouse.identity is None and mouse.model is None


def test_factory_reset_identity_drift_after_backup_prevents_reset(monkeypatch, tmp_path):
    mouse, firmware = real_mouse()
    backup = tmp_path / "before.json"
    original = mouse.identify

    def drift():
        if backup.exists():
            firmware.usb_version += 1
        return original()

    monkeypatch.setattr(mouse, "identify", drift)
    with pytest.raises(ProtocolError, match="before factory reset"):
        mouse_snapshot.factory_reset(mouse, backup)
    assert backup.exists()
    assert not any(command[0] == 14 for command in firmware.sent)


def test_factory_reset_usb_only(tmp_path):
    mouse, firmware = real_mouse()
    mouse.transport.kind = "bluetooth"
    with pytest.raises(UnsupportedDevice):
        mouse_snapshot.factory_reset(mouse, tmp_path / "backup")
    assert not firmware.sent


def test_factory_reset_post_reset_firmware_change_is_reported(monkeypatch, tmp_path):
    mouse, firmware = real_mouse()
    original = mouse.transport.send

    def changed(command, **kwargs):
        if command[0] == 14:
            firmware.usb_version += 1
            return
        return original(command, **kwargs)

    monkeypatch.setattr(mouse.transport, "send", changed)
    backup = tmp_path / "before.json"
    with pytest.raises(ProtocolError, match="post-reset verification failed.*after factory reset"):
        mouse_snapshot.factory_reset(mouse, backup)
    assert backup.exists()


def test_factory_reset_version_change_during_backup_prevents_reset(monkeypatch, tmp_path):
    mouse, firmware = real_mouse()
    original = mouse.identify
    calls = 0

    def changed():
        nonlocal calls
        calls += 1
        if calls == 2:
            firmware.usb_version += 1
        return original()

    monkeypatch.setattr(mouse, "identify", changed)
    backup = tmp_path / "before.json"
    with pytest.raises(ProtocolError, match="creating reset backup"):
        mouse_snapshot.factory_reset(mouse, backup)
    assert not backup.exists()
    assert all(command[0] == 2 for command in firmware.sent)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(schema_version=7),
        lambda value: value.update(identity={"device_id": 9999, "usb_version": 1}),
        lambda value: value.update(profile=True),
        lambda value: value["profiles"].__setitem__(
            0, {"matrix": None, "dpi": "00" * 64, "settings": {}}
        ),
        lambda value: value["profiles"].__setitem__(
            0, {"matrix": "zz", "dpi": "00" * 64, "settings": {}}
        ),
        lambda value: value["profiles"].__setitem__(
            0, {"matrix": "00" * 64, "dpi": "00" * 64, "settings": {}}
        ),
        lambda value: value.update(macros=[]),
        lambda value: value.update(limitations="test"),
    ],
)
def test_validate_rejects_malformed_schema_shapes(mutate):
    value = snapshot_template()
    mutate(value)
    with pytest.raises(ValueError):
        mouse_snapshot.validate(value)


def test_validate_rejects_wrong_boolean_setting_and_unknown_usb_settings():
    value = snapshot_template()
    value["profiles"][0]["settings"]["line_repair"] = 1
    with pytest.raises(ValueError, match="boolean"):
        mouse_snapshot.validate(value)
    value = snapshot_template(3961, None)
    del value["profiles"][0]["settings"]["sleep_bt"]
    with pytest.raises(ValueError, match="settings"):
        mouse_snapshot.validate(value)


def test_capture_rejects_non_usb_before_identify():
    mouse = FakeMouse()
    mouse.transport.kind = "bluetooth"
    with pytest.raises(UnsupportedDevice, match="USB"):
        mouse_snapshot.capture(mouse)


class _ChangingIdentity(FakeMouse):
    def __init__(self):
        super().__init__()
        self.identify_calls = 0

    def identify(self):
        self.identify_calls += 1
        if self.identify_calls == 3:
            return {"device_id": 3303, "usb_version": self.usb_version}
        return super().identify()


def test_capture_rejects_identity_drift_and_attempts_profile_cleanup():
    mouse = _ChangingIdentity()
    mouse.profile = 4
    with pytest.raises(ProtocolError, match="identity or profile changed"):
        mouse_snapshot.capture(mouse)
    assert mouse.profile == 4


def test_capture_rejects_setting_gate_mismatch_before_profile_reads():
    mouse = FakeMouse()
    original = mouse._setting_supported
    calls = 0

    def missing_once(name):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise UnsupportedDevice("not supported")
        return original(name)

    mouse._setting_supported = missing_once
    with pytest.raises(ProtocolError, match="setting gates"):
        mouse_snapshot.capture(mouse)
    assert mouse.profile == 0


def test_capture_rejects_bad_profile_matrix_or_dpi_response():
    mouse = FakeMouse()
    mouse.matrices[0] = b"short"
    with pytest.raises(ProtocolError, match="invalid length"):
        mouse_snapshot.capture(mouse)
    mouse = FakeMouse()
    bad = bytearray(mouse.dpis[0])
    bad[0] = 0x10
    mouse.dpis[0] = bytes(bad)
    with pytest.raises(ProtocolError, match="invalid length"):
        mouse_snapshot.capture(mouse)


def test_restore_capture_failure_happens_before_recovery_file(monkeypatch, tmp_path):
    mouse, firmware = real_mouse()
    requested = snapshot_template(3961, 0x0400)
    monkeypatch.setattr(
        mouse_snapshot, "capture", lambda _: (_ for _ in ()).throw(RuntimeError("capture failed"))
    )
    backup = tmp_path / "before.json"
    with pytest.raises(RuntimeError, match="capture failed"):
        mouse_snapshot.restore(mouse, requested, backup)
    assert not backup.exists()
    assert not firmware.sent


def test_restore_rejects_dpi_readback_mismatch_after_backup(monkeypatch, tmp_path):
    mouse, firmware = real_mouse()
    requested = mouse_snapshot.capture(mouse)
    original_dpi = requested["profiles"][0]["dpi"]
    changed = bytearray.fromhex(original_dpi)
    changed[2] = (changed[2] + 1) & 0xFF
    requested["profiles"][0]["dpi"] = bytes(changed).hex()
    original_write = mouse._write

    def drop_dpi(command):
        if command[0] != 0x10:
            original_write(command)

    monkeypatch.setattr(mouse, "_write", drop_dpi)
    backup = tmp_path / "before.json"
    with pytest.raises(ProtocolError, match="DPI readback differs"):
        mouse_snapshot.restore(mouse, requested, backup)
    assert backup.exists()


def test_restore_reports_profile_cleanup_failure_after_partial_write(monkeypatch, tmp_path):
    mouse, firmware = real_mouse()
    requested = mouse_snapshot.capture(mouse)
    original_profile = mouse.get_profile()
    writes_started = False

    def fail_matrix(profile, matrix):
        nonlocal writes_started
        writes_started = True
        firmware.profile = 3
        raise RuntimeError("matrix write failed")

    original_set_profile = mouse.set_profile

    def fail_cleanup(profile):
        if writes_started and profile == original_profile:
            raise RuntimeError("cleanup profile failed")
        return original_set_profile(profile)

    monkeypatch.setattr(mouse, "write_matrix", fail_matrix)
    monkeypatch.setattr(mouse, "set_profile", fail_cleanup)
    backup = tmp_path / "before.json"
    with pytest.raises(ProtocolError, match="profile cleanup failed"):
        mouse_snapshot.restore(mouse, requested, backup)
    assert backup.exists()


def test_restore_rejects_profile_drift_after_matrix_before_dpi(monkeypatch, tmp_path):
    mouse, firmware = real_mouse()
    requested = mouse_snapshot.capture(mouse)
    original_write_matrix = mouse.write_matrix

    def drift(profile, matrix):
        original_write_matrix(profile, matrix)
        firmware.profile = 7

    monkeypatch.setattr(mouse, "write_matrix", drift)
    backup = tmp_path / "before.json"
    with pytest.raises(ProtocolError, match="before DPI restore"):
        mouse_snapshot.restore(mouse, requested, backup)
    assert backup.exists()


def test_factory_reset_rejects_unsupported_identity_before_backup(tmp_path):
    mouse, firmware = real_mouse()
    firmware.model_id = 9999
    with pytest.raises(UnsupportedDevice, match="does not match"):
        mouse_snapshot.factory_reset(mouse, tmp_path / "before.json")
    assert not (tmp_path / "before.json").exists()
    assert not firmware.sent


@pytest.mark.parametrize(
    "name,value",
    [("line_repair", 1), ("debounce", -1), ("debounce", 256)],
)
def test_raw_setting_command_rejects_invalid_values(name, value):
    with pytest.raises(ValueError):
        mouse_snapshot._raw_setting_command(name, value)


@pytest.mark.parametrize("code", [True, -1, 256])
def test_raw_report_rate_command_rejects_invalid_raw_byte(code):
    with pytest.raises(ValueError, match="raw byte"):
        mouse_snapshot._raw_rate_command(code)


def test_raw_dpi_command_rejects_wrong_response_shape():
    with pytest.raises(ValueError, match="captured DPI"):
        mouse_snapshot._raw_dpi_command(bytes(64), 0)
    with pytest.raises(ValueError, match="captured DPI"):
        mouse_snapshot._raw_dpi_command(bytes([0x90]) * 63, 0)


def test_capture_rejects_short_report_rate_response():
    mouse = FakeMouse()
    mouse._query = lambda payload, expected=None: bytes(3)
    with pytest.raises(ProtocolError, match="report-rate"):
        mouse_snapshot.capture(mouse)


def test_restore_changed_matrix_dpi_scalar_and_macro_reads_back(tmp_path):
    mouse, firmware = real_mouse()
    requested = mouse_snapshot.capture(mouse)
    requested["profiles"][0]["matrix"] = (bytes([0xA5]) + bytes(63)).hex()
    dpi = bytearray.fromhex(requested["profiles"][0]["dpi"])
    dpi[2] = 2
    requested["profiles"][0]["dpi"] = dpi.hex()
    requested["profiles"][0]["settings"]["debounce"] = 7
    requested["macros"]["0"] = (bytes([0x5A]) * 256).hex()
    result = mouse_snapshot.restore(mouse, requested, tmp_path / "before.json")
    assert result["restored"] is True
    assert firmware.matrix[(0, 0)][0] == 0xA5
    assert firmware.current == 2
    assert firmware.setting_banks[0]["debounce"] == 7
    assert firmware.macros[0] == bytes([0x5A]) * 256


def test_restore_rejects_identity_drift_after_backup_before_write(monkeypatch, tmp_path):
    mouse, firmware = real_mouse()
    requested = mouse_snapshot.capture(mouse)
    monkeypatch.setattr(mouse_snapshot, "capture", lambda _: requested)
    calls = 0

    def drift():
        nonlocal calls
        calls += 1
        model_id = 3961 if calls == 1 else 3303
        return {"device_id": model_id, "usb_version": 0x0400}

    monkeypatch.setattr(mouse, "identify", drift)
    with pytest.raises(ProtocolError, match="before restore write"):
        mouse_snapshot.restore(mouse, requested, tmp_path / "before.json")


class _UnsupportedIdentityMouse(FakeMouse):
    def identify(self):
        return {"device_id": 9999, "usb_version": 1}


def test_factory_reset_rejects_identity_not_in_snapshot_models(tmp_path):
    mouse = _UnsupportedIdentityMouse()
    with pytest.raises(UnsupportedDevice, match="not supported"):
        mouse_snapshot.factory_reset(mouse, tmp_path / "before.json")
