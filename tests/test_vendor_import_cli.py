import json

from epomaker_driver import cli, snapshot
from epomaker_driver.device import Keyboard
from epomaker_driver.discovery import DeviceInfo


def record():
    return {
        "deviceType": {"id": 3059},
        "value": [
            {
                "type": "ConfigMacro",
                "original": 4,
                "macroType": "on_off",
                "repeatCount": 1,
                "macro": [],
            },
        ],
    }


def test_offline_plan_cli_reserves_other_profiles(firmware, tmp_path, capsys, monkeypatch):
    firmware.fn[1][0:4] = bytes([9, 1, 0, 0])
    current = snapshot.capture(Keyboard(firmware))
    source = tmp_path / "current.json"
    source.write_text(json.dumps(current))
    vendor = tmp_path / "vendor.json"
    vendor.write_text(json.dumps(record()))
    monkeypatch.setattr(
        cli, "select_device", lambda _: (_ for _ in ()).throw(AssertionError("offline"))
    )
    assert cli.main(["plan-vendor-import", str(vendor), "--snapshot", str(source)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["assignments"][0]["slot"] == 1
    assert not result["write_ready"]
    assert not firmware.sent


def test_import_cli_writes_selected_layer_and_recovery(
    firmware, descriptor, tmp_path, capsys, monkeypatch
):
    info = DeviceInfo("/dev/hidraw9", "Glyph", 5, 0x3151, 0x5004, descriptor, "bluetooth", 6)
    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: firmware)
    vendor = tmp_path / "vendor.json"
    vendor.write_text(json.dumps(record()))
    backup = tmp_path / "before.json"
    assert (
        cli.main(
            [
                "--device",
                info.path,
                "import-vendor-config",
                str(vendor),
                "--profile",
                "1",
                "--backup",
                str(backup),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["imported"] and result["profile"] == 1
    assert backup.exists()
    assert firmware.closed
