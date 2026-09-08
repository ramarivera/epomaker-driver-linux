"""HE75 Mag 2520 has Windows-only Fn and catalog-specific magnetic ranges."""

import json

import pytest
from test_he_recovery_cli import install

from epomaker_driver import cli


def test_he75mag_cli_switch_and_four_mm_travel(monkeypatch, capsys):
    _, fw, info = install(monkeypatch, 2520)
    prefix = ["--device", info.path]
    assert cli.main(prefix + ["status"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["profiles"] == 4
    assert "knob_slots" not in data
    assert cli.main(prefix + ["switch-type", "磁白轴", "1"]) == 0
    capsys.readouterr()
    assert fw.fields[252][1] == 8
    assert (
        cli.main(
            prefix
            + [
                "magnetic-key",
                "1",
                "--travel",
                "4",
                "--deadzone",
                "0.02",
                "--fire",
                "--rapid-press",
                "0.015",
                "--rapid-lift",
                "2",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert fw.fields[0][2:4] == (800).to_bytes(2, "little")
    assert fw.fields[6][2:4] == (4).to_bytes(2, "little")
    assert fw.fields[2][2:4] == (3).to_bytes(2, "little")
    assert cli.main(prefix + ["key", "1", "00000400", "--fn"]) == 0
    capsys.readouterr()
    assert fw.fn[0, 0][4:8] == bytes.fromhex("00000400")


@pytest.mark.parametrize(
    "command",
    [
        ["matrix", "--fn", "--os-mode", "1"],
        ["key", "1", "00000400", "--fn", "--os-mode", "1"],
        ["get-light", "--side"],
        ["debounce", "3"],
        ["magnetic-key", "1", "--travel", "2.01"],
        ["magnetic-key", "1", "--deadzone", "0.01"],
        ["magnetic-key", "1", "--rapid-press", "0.005"],
        ["switch-type", "云玉磁轴", "1"],
    ],
)
def test_he75mag_cli_rejects_unexposed_or_out_of_range(monkeypatch, capsys, command):
    _, fw, info = install(monkeypatch, 2520)
    assert cli.main(["--device", info.path] + command) == 1
    assert "error" in capsys.readouterr().err
    assert not fw.sent
