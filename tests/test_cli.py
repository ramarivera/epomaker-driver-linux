import json

import pytest

from epomaker_driver import cli, profiles
from epomaker_driver.discovery import DeviceInfo


@pytest.fixture
def cli_device(monkeypatch, descriptor, firmware):
    info = DeviceInfo("/dev/hidraw9", "Glyph", 5, 0x3151, 0x5004, descriptor, "bluetooth", 6)
    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: firmware)
    return info


@pytest.mark.parametrize(
    "arguments",
    [
        ["discover"],
        ["models"],
        ["identify"],
        ["status"],
        ["get-light"],
        ["get-light", "--side"],
        ["light", "solid", "--rgb", "#abcdef"],
        ["light", "wave", "--side"],
        ["get-sleep"],
        ["sleep", "120", "240", "1800", "3600"],
        ["matrix"],
        ["matrix", "--fn", "--os-mode", "1"],
        ["key", "9", "00000500"],
        ["key", "9", "00000600", "--fn", "--os-mode", "1"],
        ["profile", "1"],
        ["debounce", "10"],
        ["clock"],
    ],
)
def test_cli_commands(arguments, cli_device, firmware, capsys):
    assert cli.main(["--device", cli_device.path, *arguments]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value is not None
    if arguments[0] not in ("discover", "models"):
        assert firmware.closed


def test_backup_and_inspect(cli_device, tmp_path, capsys):
    path = tmp_path / "backup.json"
    assert cli.main(["--device", cli_device.path, "backup", str(path)]) == 0
    value = json.loads(path.read_text())
    assert value["identity"]["device_id"] == 3059
    assert len(bytes.fromhex(value["matrices"][2])) == 512
    assert len(value["fn"]) == 2
    assert value["limitations"]
    capsys.readouterr()
    assert cli.main(["inspect-profile", str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == value
    assert cli.main(["--device", cli_device.path, "backup", str(path)]) == 1
    assert "FileExistsError" in capsys.readouterr().err


def test_cli_errors(cli_device, capsys, tmp_path):
    assert cli.main(["identify"]) == 1
    assert "choose --device" in capsys.readouterr().err
    assert cli.main(["--device", "/dev/not-a-device", "identify"]) == 1
    assert "not a supported command collection" in capsys.readouterr().err
    assert cli.main(["--device", cli_device.path, "key", "9", "badhex"]) == 1
    assert "ValueError" in capsys.readouterr().err
    assert cli.main(["inspect-profile", str(tmp_path / "missing")]) == 1
    assert "FileNotFoundError" in capsys.readouterr().err
    assert cli.integer("0xff") == 255
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0


def test_compressed_import(tmp_path, capsys):
    path = tmp_path / "vendor.bin"
    path.write_bytes(profiles.encode({"name": "example", "unknown": True}))
    assert cli.main(["inspect-profile", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["unknown"]
