"""CLI integration for internal model 3746, distinct from other HE60 variants."""

import json

import pytest
from test_he import Firmware, keyboard

from epomaker_driver import cli
from epomaker_driver.discovery import DeviceInfo


def install(monkeypatch):
    fw = Firmware(model_id=3746)
    fw.usb_version = 0x0500
    info = DeviceInfo("/dev/he60", "HE60", 3, 0x3151, 0x5029, b"", "usb", 0)

    class Opened:
        def __enter__(self):
            return keyboard(fw, product=0x5029).transport

        def __exit__(self, *_):
            pass

    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: Opened())
    return fw, info


def test_he60_cli_profiles_switches_and_catalog_travel(monkeypatch, capsys):
    fw, info = install(monkeypatch)
    prefix = ["--device", info.path]
    assert cli.main(prefix + ["identify"]) == 0
    assert json.loads(capsys.readouterr().out)["device_id"] == 3746
    assert cli.main(prefix + ["profile", "3"]) == 0
    capsys.readouterr()
    for value, code in [("云玉磁轴", 93), ("天青轴", 55)]:
        assert cli.main(prefix + ["switch-type", value, "1"]) == 0
        capsys.readouterr()
        assert fw.fields[252][1] == code
    assert (
        cli.main(
            prefix
            + [
                "magnetic-key",
                "1",
                "--travel",
                "3.4",
                "--fire",
                "--rapid-press",
                "0.005",
                "--rapid-lift",
                "2.5",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert fw.fields[0][2:4] == (680).to_bytes(2, "little")
    assert fw.fields[2][2:4] == (1).to_bytes(2, "little")
    assert fw.fields[3][2:4] == (500).to_bytes(2, "little")
    assert cli.main(prefix + ["key", "1", "00000400", "--profile", "3", "--submode", "3"]) == 0
    assert fw.matrices[3, 3][4:8] == bytes.fromhex("00000400")


@pytest.mark.parametrize(
    "command",
    [
        ["switch-type", "33", "1"],
        ["switch-type", "0", "1"],
        ["magnetic-key", "1", "--travel", "3.405"],
        ["magnetic-key", "1", "--deadzone", "1.005"],
        ["get-light", "--side"],
        ["get-sleep"],
        ["debounce", "3"],
    ],
)
def test_he60_cli_rejects_unadvertised_features_and_invalid_limits(monkeypatch, capsys, command):
    fw, info = install(monkeypatch)
    assert cli.main(["--device", info.path] + command) == 1
    assert "error" in capsys.readouterr().err
    assert not fw.sent
