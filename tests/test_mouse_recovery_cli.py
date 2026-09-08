"""Schema-8 recovery through the public CLI and USB firmware simulator."""

import json

import pytest
from test_mouse import USB
from test_mouse_cli import install
from test_mouse_settings import SettingsFirmware

from epomaker_driver import cli, mouse_snapshot
from epomaker_driver.mouse import Mouse
from epomaker_driver.transport import Transport


def setup(monkeypatch, model):
    _, _, info = install(monkeypatch, model)
    fw = SettingsFirmware(model)

    def opened(_):
        return Transport(USB(fw), "usb", sleep=lambda _: None)

    monkeypatch.setattr(cli.Transport, "open", opened)
    return fw, info


@pytest.mark.parametrize("model", [3961, 3303, 3304, 3929, 3919])
def test_backup_restore_cli_all_mouse_models(monkeypatch, capsys, tmp_path, model):
    fw, info = setup(monkeypatch, model)
    fw.profile = 7
    path, rollback = tmp_path / "snapshot.json", tmp_path / "before.json"
    prefix = ["--device", info.path]
    assert cli.main(prefix + ["backup", str(path)]) == 0
    capsys.readouterr()
    saved = json.loads(path.read_text())
    assert saved["schema_version"] == 8
    assert len(saved["profiles"]) == 8
    assert len(saved["macros"]) == 50
    assert fw.profile == 7
    assert path.stat().st_mode & 0o777 == 0o600
    fw.matrix[3, 0] = b"abcd"
    fw.values["sleep_bt"] = 50
    fw.macros[49] = bytes([9]) * 256
    fw.dpi_banks[6]["levels"][1]["rgb"] = 0xFFEEDD
    assert cli.main(prefix + ["restore", str(path), "--backup", str(rollback)]) == 0
    capsys.readouterr()
    assert rollback.exists()
    assert rollback.stat().st_mode & 0o777 == 0o600
    mouse = Mouse(Transport(USB(fw), "usb", sleep=lambda _: None), product_id=fw.product_id)
    actual = mouse_snapshot.capture(mouse)
    assert actual == saved


def test_mouse_backup_noclobber(monkeypatch, capsys, tmp_path):
    _, info = setup(monkeypatch, 3961)
    path = tmp_path / "existing.json"
    path.write_text("keep")
    assert cli.main(["--device", info.path, "backup", str(path)]) == 1
    capsys.readouterr()
    assert path.read_text() == "keep"
    assert cli.main(["--device", info.path, "backup", str(path), "--overwrite"]) == 0
    assert json.loads(path.read_text())["schema_version"] == 8


def test_mouse_restore_rejects_malformed_before_open(monkeypatch, capsys, tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"schema_version":8}')
    monkeypatch.setattr(cli.Transport, "open", lambda _: pytest.fail("must reject before HID"))
    assert cli.main(["restore", str(path), "--backup", str(tmp_path / "before")]) == 1
    assert "error" in capsys.readouterr().err


def test_mouse_snapshot_cannot_restore_to_keyboard(monkeypatch, capsys, tmp_path):
    fw = SettingsFirmware(3961)
    mouse = Mouse(Transport(USB(fw), "usb", sleep=lambda _: None), product_id=fw.product_id)
    path = tmp_path / "mouse.json"
    path.write_text(json.dumps(mouse_snapshot.capture(mouse)))
    from epomaker_driver.discovery import DeviceInfo

    info = DeviceInfo("/dev/keyboard", "Keyboard", 3, 0x3151, 0x5002, b"", "usb", 0)
    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: pytest.fail("must reject before HID"))
    assert (
        cli.main(
            ["--device", info.path, "restore", str(path), "--backup", str(tmp_path / "before")]
        )
        == 1
    )
    assert "schema 8" in capsys.readouterr().err


class BankedSettingsFirmware(SettingsFirmware):
    @property
    def values(self):
        return self.setting_banks[self.profile]

    @values.setter
    def values(self, value):
        self.setting_banks = {p: dict(value) for p in range(8)}

    def __init__(self, model):
        super().__init__(model)
        self.rate_codes = {p: 1 for p in range(8)}

    def exchange(self, command):
        if command[0] == 0x88:
            return bytes([0x88, self.rate_codes[self.profile]]) + bytes(62)
        return super().exchange(command)

    def send(self, command):
        if command[0] == 8:
            self.sent.append(bytes(command))
            self.rate_codes[self.profile] = command[1]
        else:
            super().send(command)


def test_profile_banked_settings_and_raw_values_restore_via_usb(tmp_path):
    fw = BankedSettingsFirmware(3961)
    mouse = Mouse(Transport(USB(fw), "usb", sleep=lambda _: None), product_id=fw.product_id)
    for p in range(8):
        fw.setting_banks[p]["sleep_24"] = p * 1000
        fw.setting_banks[p]["debounce"] = 250 + p % 6
        fw.setting_banks[p]["lod"] = 200 + p
        fw.rate_codes[p] = 200 + p
        fw.dpi_banks[p]["levels"][7] = {"x": 65535, "y": 65534, "rgb": 0x010203 + p}
    fw.profile = 5
    before = mouse_snapshot.capture(mouse)
    for p in range(8):
        fw.setting_banks[p]["sleep_24"] = 1
        fw.setting_banks[p]["debounce"] = 1
        fw.setting_banks[p]["lod"] = 0
        fw.rate_codes[p] = 1
        fw.dpi_banks[p]["levels"][7]["rgb"] = 0
    mouse_snapshot.restore(mouse, before, tmp_path / "before.json")
    assert mouse_snapshot.capture(mouse) == before
    assert fw.profile == 5


def test_noop_mouse_restore_skips_configuration_payloads(tmp_path):
    fw = SettingsFirmware()
    mouse = Mouse(Transport(USB(fw), "usb", sleep=lambda _: None), product_id=fw.product_id)
    before = mouse_snapshot.capture(mouse)
    fw.sent.clear()
    mouse_snapshot.restore(mouse, before, tmp_path / "before.json")
    assert all(command[0] == 2 for command in fw.sent)


def test_restore_ignores_changing_dpi_reply_metadata_and_limitations(monkeypatch, tmp_path):
    fw = SettingsFirmware()
    mouse = Mouse(Transport(USB(fw), "usb", sleep=lambda _: None), product_id=fw.product_id)
    original = fw.exchange
    serial = 0

    def dynamic(command):
        nonlocal serial
        raw = original(command)
        if command[0] == 0x90:
            serial += 1
            raw = bytearray(raw)
            raw[1] = 0  # Response profile echo is not a request-address field.
            raw[4:8] = (serial & 0xFFFFFFFF).to_bytes(4, "little")
        return bytes(raw)

    monkeypatch.setattr(fw, "exchange", dynamic)
    before = mouse_snapshot.capture(mouse)
    before["limitations"] = ["edited explanatory text"]
    fw.levels[1]["x"] = 2000
    mouse_snapshot.restore(mouse, before, tmp_path / "before.json")
    assert fw.levels[1]["x"] == 900
    assert fw.profile == before["profile"]


@pytest.mark.parametrize("model", [3961, 3303, 3304, 3929, 3919])
def test_mouse_factory_reset_cli_saves_before_reset_and_preserves_post_profile(
    monkeypatch, capsys, tmp_path, model
):
    _, info = setup(monkeypatch, model)
    fw = SettingsFirmware(model)
    fw.profile = 7
    backup = tmp_path / "before-reset.json"
    send = fw.send
    waits = []

    def reset(command):
        if command[0] == 0x0E:
            saved = json.loads(backup.read_text())
            assert saved["profile"] == 7
            assert len(saved["macros"]) == 50
            assert len(saved["profiles"]) == 8
            assert command == bytes([14]) + bytes(6) + bytes([241]) + bytes(56)
            fw.sent.append(bytes(command))
            fw.profile = 3  # Arbitrary observed post-reset value, not assumed vendor defaults.
            fw.values["debounce"] = 2
        else:
            send(command)

    monkeypatch.setattr(fw, "send", reset)
    monkeypatch.setattr(
        cli.Transport, "open", lambda _: Transport(USB(fw), "usb", sleep=waits.append)
    )
    assert cli.main(["--device", info.path, "factory-reset", "--backup", str(backup)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["factory_defaults_verified"] is False
    assert fw.profile == 3
    assert waits.count(0.3) == 1
    assert sum(command[0] == 14 for command in fw.sent) == 1
    assert all(command[0] in (2, 14) for command in fw.sent)
