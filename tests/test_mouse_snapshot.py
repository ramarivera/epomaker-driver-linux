"""Schema-8 CH585 snapshot validation and capture tests."""

from __future__ import annotations

import copy

import pytest
from test_mouse import USB
from test_mouse_recovery_cli import BankedSettingsFirmware

from epomaker_driver import mouse_snapshot
from epomaker_driver.errors import ProtocolError
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
