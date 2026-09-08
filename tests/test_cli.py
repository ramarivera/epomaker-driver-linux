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


@pytest.mark.parametrize(
    "args,expected",
    [
        (["bind-key", "10", "c", "--modifier", "ctrl"], "00010600"),
        (["bind-media", "10", "volume-up"], "0300e900"),
        (["bind-mouse", "10", "left"], "0100f000"),
        (["bind-macro", "10", "5", "--mode", "held"], "09020500"),
        (["disable-key", "10"], "00000000"),
    ],
)
def test_semantic_binding_cli(args, expected, cli_device, capsys):
    prefix = ["--device", cli_device.path]
    assert cli.main([*prefix, *args]) == 0
    assert json.loads(capsys.readouterr().out)["raw"] == expected
    assert cli.main([*prefix, "matrix", "--decoded"]) == 0
    assert json.loads(capsys.readouterr().out)["slots"][10]["raw"] == expected


def test_decoded_macro_cli_and_action_catalog(cli_device, firmware, capsys):
    from epomaker_driver import macros

    value = {"repeat": 2, "events": [{"type": "mouse_move", "dx": 1, "dy": -1, "delay_ms": 10}]}
    firmware.macros[0] = bytearray(macros.encode(**value))
    assert cli.main(["--device", cli_device.path, "get-macro", "0", "--decoded"]) == 0
    assert json.loads(capsys.readouterr().out) == value
    assert cli.main(["actions"]) == 0
    assert "volume-up" in json.loads(capsys.readouterr().out)["media"]


def test_animation_cli(cli_device, firmware, tmp_path, capsys):
    from PIL import Image

    path = tmp_path / "animation.gif"
    Image.new("RGB", (2, 2), "red").save(
        path, save_all=True, append_images=[Image.new("RGB", (2, 2), "green")], duration=80
    )
    assert cli.main(["--device", cli_device.path, "animation", str(path), "--fit"]) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "frames": 2, "frame_delay_ms": 80}
    assert len(firmware.sent) == 4342


def test_host_info_and_bounded_display_refresh(cli_device, firmware, monkeypatch, capsys):
    value = {
        "disk_available": 0,
        "disk_total": 1024**3,
        "memory_used": 0,
        "memory_total": 1024**3,
        "cpu_usage": 20,
        "cpu_temperature": None,
        "network_up": 0,
        "network_down": 0,
        "warnings": [],
    }

    class Collector:
        def __init__(self, **kwargs):
            pass

        def collect(self):
            return value

    monkeypatch.setattr(cli.system_info, "Collector", Collector)
    sleeps = []
    monkeypatch.setattr(cli.time, "sleep", sleeps.append)
    assert cli.main(["host-info"]) == 0
    assert json.loads(capsys.readouterr().out) == value
    assert (
        cli.main(["--device", cli_device.path, "system-info", "--count", "2", "--interval", "1"])
        == 0
    )
    assert json.loads(capsys.readouterr().out)["sent"] == 2
    assert sleeps == [1]
    assert [p[0] for p in firmware.sent] == [0x22, 0x22]
    assert firmware.closed
    assert cli.main(["--device", cli_device.path, "system-info", "--count", "0"]) == 1
    assert "count must" in capsys.readouterr().err

    def interrupt(*_):
        raise KeyboardInterrupt()

    monkeypatch.setattr(cli, "execute", interrupt)
    assert cli.main(["host-info"]) == 130
    assert json.loads(capsys.readouterr().err)["interrupted"]


def test_display_bank_cli(cli_device, firmware, tmp_path):
    from PIL import Image

    path = tmp_path / "bank.png"
    Image.new("RGB", (428, 142), "blue").save(path)
    assert cli.main(["--device", cli_device.path, "screen", str(path), "--bank", "5"]) == 0
    assert all(p[1:3] == bytes([4, 1]) for p in firmware.sent if p[0] == 0x25)
    assert cli.main(["--device", cli_device.path, "display-language-toggle"]) == 0
    assert firmware.sent[-1][:2] == bytes([0x27, 1])


def test_factory_reset_cli(cli_device, firmware, tmp_path, capsys):
    destination = tmp_path / "recovery.json"
    assert (
        cli.main(["--device", cli_device.path, "factory-reset", "--backup", str(destination)]) == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["reset_sent"] and result["previous_configuration"] == str(destination)
    assert firmware.sent[-1][:8] == bytes.fromhex("01000000000000fe")
