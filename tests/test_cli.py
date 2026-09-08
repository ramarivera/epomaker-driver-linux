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


def test_macro_write_and_read(cli_device, firmware, tmp_path, capsys):
    path = tmp_path / "macro.json"
    path.write_text(
        json.dumps(
            {
                "repeat": 1,
                "events": [
                    {"hid_usage": 4, "down": True, "delay_ms": 10},
                    {"hid_usage": 4, "down": False, "delay_ms": 300},
                ],
            }
        )
    )
    prefix = ["--device", cli_device.path]
    assert cli.main([*prefix, "macro", "3", str(path)]) == 0
    capsys.readouterr()
    assert cli.main([*prefix, "get-macro", "3"]) == 0
    data = bytes.fromhex(json.loads(capsys.readouterr().out)["data"])
    assert data[:8] == bytes.fromhex("0100048a04002c01")
    before = list(firmware.sent)
    for value in (
        {},
        {"repeat": 1, "events": [{}]},
        {"repeat": 1, "events": [{"hid_usage": 4, "down": "false", "delay_ms": 10}]},
    ):
        path.write_text(json.dumps(value))
        assert cli.main([*prefix, "macro", "3", str(path)]) == 1
        assert "ValueError" in capsys.readouterr().err
        assert firmware.sent == before


def test_screen_cli(cli_device, firmware, tmp_path):
    from PIL import Image

    path = tmp_path / "screen.png"
    Image.new("RGB", (428, 142), "red").save(path)
    assert cli.main(["--device", cli_device.path, "screen", str(path)]) == 0
    chunks = [p for p in firmware.sent if p[0] == 0x25]
    assert len(chunks) == 2171
    assert sum(p[6] for p in chunks) == 121552


@pytest.mark.parametrize(
    "arguments",
    [
        ["get-options"],
        ["options", "--system", "mac", "--wasd-swap"],
        ["options", "--no-wasd-swap"],
        ["get-auto-os"],
        ["auto-os", "on"],
        ["auto-os", "off"],
    ],
)
def test_options_cli(arguments, cli_device):
    assert cli.main(["--device", cli_device.path, *arguments]) == 0


def test_restore_cli(cli_device, tmp_path, firmware):
    prefix = ["--device", cli_device.path]
    source = tmp_path / "snapshot.json"
    recovery = tmp_path / "before.json"
    assert cli.main([*prefix, "backup", str(source)]) == 0
    firmware.profile = 2
    assert cli.main([*prefix, "restore", str(source), "--backup", str(recovery)]) == 0
    assert firmware.profile == 0
    assert json.loads(recovery.read_text())["profile"] == 2


@pytest.mark.parametrize("activate", [False, True])
def test_picture_cli(cli_device, firmware, tmp_path, capsys, activate):
    prefix = ["--device", cli_device.path]
    path = tmp_path / "colors.json"
    value = {"colors": ["123456"] * 126}
    path.write_text(json.dumps(value))
    args = [*prefix, "picture", "4", str(path)]
    assert cli.main(args + (["--activate"] if activate else [])) == 0
    capsys.readouterr()
    assert cli.main([*prefix, "get-picture", "4"]) == 0
    assert json.loads(capsys.readouterr().out) == value
    assert cli.main([*prefix, "picture-key", "4", "125", "#abcdef"]) == 0
    assert firmware.pictures[4][375:378] == bytes.fromhex("abcdef")
    if activate:
        assert firmware.light[1] == 13 and firmware.light[4] == 0x40
    before = list(firmware.sent)
    for invalid in ({}, {"colors": ["ffffff"]}, {"colors": [3] * 126}):
        path.write_text(json.dumps(invalid))
        assert cli.main(args) == 1
        assert firmware.sent == before
