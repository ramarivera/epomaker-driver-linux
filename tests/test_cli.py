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
        ["clock"],
    ],
)
def test_cli_commands(arguments, cli_device, firmware, capsys):
    assert cli.main(["--device", cli_device.path, *arguments]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value is not None
    if arguments[0] not in ("discover", "models"):
        assert firmware.closed


def test_glyph_debounce_cli_is_rejected(cli_device, firmware, capsys):
    assert cli.main(["--device", cli_device.path, "debounce", "10"]) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["error"] == "UnsupportedDevice"
    assert "Glyph does not expose a debounce control" in error["message"]
    assert firmware.closed and not firmware.sent


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
    for invalid in (
        [],
        {},
        {"colors": ["ffffff"]},
        {"colors": [3] * 126},
        {"colors": ["abcdef"] * 128},
    ):
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


def test_rt85_fourth_profile(cli_device, firmware, capsys):
    from epomaker_driver.models import default_matrix

    firmware.model_id = 2895
    firmware.matrices = [bytearray(default_matrix(2895)) for _ in range(4)]
    prefix = ["--device", cli_device.path]
    assert cli.main([*prefix, "profile", "3"]) == 0
    assert firmware.profile == 3
    capsys.readouterr()
    assert cli.main([*prefix, "key", "9", "00000500", "--profile", "3"]) == 0
    assert bytes(firmware.matrices[3][36:40]) == bytes([0, 0, 5, 0])
    capsys.readouterr()
    assert cli.main([*prefix, "profile", "4"]) != 0


def test_rt85_display_detects_model_before_conversion(cli_device, firmware, tmp_path):
    from PIL import Image

    firmware.model_id = 2895
    path = tmp_path / "rt85.png"
    Image.new("RGB", (320, 172), "red").save(path)
    prefix = ["--device", cli_device.path]
    assert cli.main([*prefix, "screen", str(path), "--bank", "5"]) == 0
    assert firmware.sent[0][1:4] == bytes([4, 1, 0])
    assert len(firmware.sent) == 1966
    firmware.sent.clear()
    Image.new("RGB", (428, 142), "red").save(path)
    assert cli.main([*prefix, "screen", str(path)]) != 0
    assert not firmware.sent
    gif = tmp_path / "rt85.gif"
    Image.new("RGB", (2, 2), "red").save(
        gif, save_all=True, append_images=[Image.new("RGB", (2, 2), "blue")], duration=80
    )
    assert cli.main([*prefix, "animation", str(gif), "--fit"]) == 0
    assert len(firmware.sent) == 3932


def test_rt85_lighting_and_os_cli(cli_device, firmware):
    firmware.model_id = 2895
    prefix = ["--device", cli_device.path]
    for args in [
        ["light", "wave", "--side", "--speed", "4"],
        ["options", "--system", "mac"],
        ["auto-os", "on"],
        ["get-picture", "4"],
    ]:
        assert cli.main([*prefix, *args]) == 0
    assert firmware.options[1] == 1 and firmware.auto_os
    before = len(firmware.sent)
    assert cli.main([*prefix, "light", "snake", "--side"]) != 0
    assert len(firmware.sent) == before


def test_rt85_backup_restore_reset_cli(cli_device, firmware, tmp_path):
    from epomaker_driver.models import default_matrix

    firmware.model_id = 2895
    firmware.matrices = [bytearray(default_matrix(2895)) for _ in range(4)]
    firmware.profile = 3
    prefix = ["--device", cli_device.path]
    original = tmp_path / "rt85.json"
    assert cli.main([*prefix, "backup", str(original)]) == 0
    value = json.loads(original.read_text())
    assert value["schema_version"] == 4 and len(value["matrices"]) == 4
    firmware.profile = 0
    assert (
        cli.main([*prefix, "restore", str(original), "--backup", str(tmp_path / "before.json")])
        == 0
    )
    assert firmware.profile == 3
    assert cli.main([*prefix, "factory-reset", "--backup", str(tmp_path / "reset.json")]) == 0
    assert firmware.sent[-1][0] == 1


def test_rt75_core_cli(cli_device, firmware):
    firmware.model_id = 3223
    prefix = ["--device", cli_device.path]
    for args in [
        ["profile", "2"],
        ["debounce", "10"],
        ["sleep", "60", "120", "600", "1200"],
        ["status"],
        ["key", "9", "00000500", "--fn", "--os-mode", "1"],
    ]:
        assert cli.main([*prefix, *args]) == 0
    assert firmware.profile == 2 and firmware.fn[1][36:40] == bytes([0, 0, 5, 0])
    before = len(firmware.sent)
    assert cli.main([*prefix, "sleep", "0", "120", "600", "1200"]) != 0
    assert len(firmware.sent) == before


def test_rt75_display_cli(cli_device, firmware, tmp_path):
    from PIL import Image

    firmware.model_id = 3223
    prefix = ["--device", cli_device.path]
    path = tmp_path / "square.png"
    Image.new("RGB", (240, 240), "red").save(path)
    assert cli.main([*prefix, "screen", str(path), "--bank", "5"]) == 0
    assert len(firmware.sent) == 2058
    assert firmware.sent[0][1:4] == bytes([4, 1, 0])
    assert cli.main([*prefix, "clock"]) == 0
    assert cli.main([*prefix, "light", "off"]) != 0


def test_rt75_recovery_cli(cli_device, firmware, tmp_path):
    firmware.model_id = 3223
    prefix = ["--device", cli_device.path]
    path = tmp_path / "rt75.json"
    assert cli.main([*prefix, "backup", str(path)]) == 0
    value = json.loads(path.read_text())
    assert value["side_light"] is None and value["schema_version"] == 4
    assert (
        cli.main([*prefix, "restore", str(path), "--backup", str(tmp_path / "recovery.json")]) == 0
    )
    assert cli.main([*prefix, "factory-reset", "--backup", str(tmp_path / "reset.json")]) == 0
    assert firmware.sent[-1][0] == 1


@pytest.mark.parametrize("model_id", [3858, 3633, 3673, 3573, 3674])
def test_ry6602_core_cli(cli_device, firmware, model_id):
    from epomaker_driver.models import default_matrix, model_by_id

    firmware.model_id = model_id
    firmware.matrices = [
        bytearray(default_matrix(model_id)) for _ in range(model_by_id(model_id)["layer"])
    ]
    last = len(firmware.matrices) - 1
    prefix = ["--device", cli_device.path]
    assert cli.main([*prefix, "profile", str(last)]) == 0
    assert cli.main([*prefix, "key", "9", "00000500", "--profile", str(last)]) == 0
    assert firmware.matrices[last][36:40] == bytes([0, 0, 5, 0])
    assert cli.main([*prefix, "status"]) == 0


@pytest.mark.parametrize("model_id", [3858, 3633, 3673, 3573, 3674])
def test_ry6602_three_timer_cli(cli_device, firmware, model_id, capsys):
    firmware.model_id = model_id
    firmware.sleep_data[14:16] = bytes.fromhex("faff")
    prefix = ["--device", cli_device.path]
    assert cli.main([*prefix, "sleep", "600", "1200", "1800"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {"bluetooth": 600, "dongle": 1200, "deep_bluetooth": 1800}
    assert firmware.sleep_data[14:16] == bytes.fromhex("faff")
    before = len(firmware.sent)
    assert cli.main([*prefix, "sleep", "600", "1200", "1800", "2400"]) != 0
    assert len(firmware.sent) == before


def test_glyph_still_requires_four_sleep_values(cli_device, firmware):
    assert cli.main(["--device", cli_device.path, "sleep", "60", "120", "600"]) != 0
    assert not firmware.sent


@pytest.mark.parametrize("model_id,width", [(3858, 33), (3673, 7), (3674, 7)])
def test_rgb24_screen_cli(cli_device, firmware, tmp_path, model_id, width):
    from PIL import Image

    firmware.model_id = model_id
    path = tmp_path / "led.png"
    Image.new("RGB", (width, 7), (0x12, 0x34, 0x56)).save(path)
    assert cli.main(["--device", cli_device.path, "screen", str(path), "--bank", "5"]) == 0
    assert firmware.sent[0][0:4] == bytes([0x29, 4, 1, 0])
    assert b"".join(p[8 : 8 + p[6]] for p in firmware.sent) == bytes.fromhex("123456") * (width * 7)


@pytest.mark.parametrize("model_id", [3858, 3633, 3673, 3573, 3674])
def test_ry6602_recovery_cli(cli_device, firmware, tmp_path, model_id):
    from epomaker_driver import codec
    from epomaker_driver.models import default_matrix, model_by_id

    firmware.model_id = model_id
    firmware.matrices = [
        bytearray(default_matrix(model_id)) for _ in range(model_by_id(model_id)["layer"])
    ]
    firmware.sleep_data = bytearray(codec.sleep_times(600, 1200, 1800, 3600))
    firmware.side_light = bytearray(codec.light("breathing", side=True))
    prefix = ["--device", cli_device.path]
    path = tmp_path / "saved.json"
    assert cli.main([*prefix, "backup", str(path)]) == 0
    assert json.loads(path.read_text())["schema_version"] == 5
    assert (
        cli.main([*prefix, "restore", str(path), "--backup", str(tmp_path / "recovery.json")]) == 0
    )
    assert cli.main([*prefix, "factory-reset", "--backup", str(tmp_path / "reset.json")]) == 0
    assert firmware.sent[-1][0] == 1
