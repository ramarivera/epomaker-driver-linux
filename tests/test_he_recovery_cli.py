import json

import pytest
from he_snapshot_firmware import snapshot_keyboard

from epomaker_driver import cli, he_snapshot, profiles
from epomaker_driver.discovery import DeviceInfo


def install(monkeypatch, model=3692):
    kb, fw = snapshot_keyboard(model)
    info = DeviceInfo("/dev/magnetic", "HE", 3, 0x3151, kb.product_id, b"", "usb", 0)

    class Opened:
        def __enter__(self):
            return kb.transport

        def __exit__(self, *_):
            return None

    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: Opened())
    return kb, fw, info


@pytest.mark.parametrize("model", [3727, 3759, 2586, 2761, 3692, 3703, 3746, 3365, 4071])
def test_cli_backup_restore_schema7(model, monkeypatch, tmp_path, capsys):
    kb, fw, info = install(monkeypatch, model)
    path, backup = tmp_path / "config", tmp_path / "previous"
    assert cli.main(["--device", info.path, "backup", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["saved"] == str(path)
    value = profiles.decode(path.read_bytes())
    assert value["schema_version"] == 7
    fw.macros[255] = bytes(256)
    assert cli.main(["--device", info.path, "restore", str(path), "--backup", str(backup)]) == 0
    assert json.loads(capsys.readouterr().out)["restored"]
    assert fw.macros[255] == bytes([255]) * 256
    assert profiles.decode(backup.read_bytes())["macros"]["255"] == bytes(256).hex()


def test_schema7_on_other_family_rejected_before_open(monkeypatch, tmp_path, capsys):
    kb, _ = snapshot_keyboard()
    path = tmp_path / "config"
    profiles.save(path, he_snapshot.capture(kb))
    info = DeviceInfo("/dev/other", "Other", 3, 0x3151, 0x5002, b"", "usb", 0)
    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: pytest.fail("must reject before open"))
    assert (
        cli.main(
            ["--device", info.path, "restore", str(path), "--backup", str(tmp_path / "backup")]
        )
        == 1
    )
    assert "schema 7" in capsys.readouterr().err


def test_invalid_schema7_rejected_before_discovery(monkeypatch, tmp_path, capsys):
    path = tmp_path / "bad"
    profiles.save(path, {"schema_version": 7})
    monkeypatch.setattr(cli, "discover", lambda: pytest.fail("must validate before discovery"))
    assert cli.main(["restore", str(path), "--backup", str(tmp_path / "backup")]) == 1
    assert "schema-7" in capsys.readouterr().err
