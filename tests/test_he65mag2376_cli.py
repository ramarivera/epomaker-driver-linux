"""HE65 Mag magnetic/knob commands through the shared CLI."""

import json

import pytest
from test_he_recovery_cli import install

from epomaker_driver import cli


def test_magnetic_and_mac_fn_commands(monkeypatch, capsys):
    _, fw, info = install(monkeypatch, 2376)
    prefix = ["--device", info.path]
    assert (
        cli.main(
            prefix
            + [
                "magnetic-key",
                "1",
                "--travel",
                "4",
                "--fire",
                "--rapid-press",
                "0.015",
                "--rapid-lift",
                "0.02",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert fw.fields[0][2:4] == (800).to_bytes(2, "little")
    assert fw.fields[2][2:4] == (3).to_bytes(2, "little")
    assert cli.main(prefix + ["key", "1", "00000400", "--fn", "--os-mode", "1"]) == 0
    capsys.readouterr()
    assert fw.fn[0, 1][4:8] == bytes.fromhex("00000400")
    assert cli.main(prefix + ["status"]) == 0
    assert json.loads(capsys.readouterr().out)["knob_slots"] == {
        "volume-up": 90,
        "volume-down": 91,
        "mute": 92,
    }


@pytest.mark.parametrize(
    "command",
    [
        ["switch-type", "高特", "1"],
        ["key", "90", "00000400", "--fn"],
        ["key", "90", "09020000"],
        ["magnetic-key", "90", "--travel", "2"],
        ["snap", "90", "1"],
        ["get-light", "--side"],
        ["debounce", "3"],
    ],
)
def test_unavailable_controls_rejected_before_payload(monkeypatch, capsys, command):
    _, fw, info = install(monkeypatch, 2376)
    assert cli.main(["--device", info.path] + command) == 1
    assert "error" in capsys.readouterr().err
    assert not fw.sent
