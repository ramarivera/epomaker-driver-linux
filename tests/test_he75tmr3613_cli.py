"""TMR 3613 uses two profiles and its own switch and travel catalog."""

import json

import pytest
from test_he_recovery_cli import install

from epomaker_driver import cli


def test_tmr3613_cli_profile_switch_travel_sleep(monkeypatch, capsys):
    _, fw, info = install(monkeypatch, 3613)
    prefix = ["--device", info.path]
    assert cli.main(prefix + ["status"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["profiles"] == 2
    assert "knob_slots" not in value and "switch_display_names" not in value
    assert cli.main(prefix + ["profile", "1"]) == 0
    capsys.readouterr()
    for name, code in [("云玉磁轴", 93), ("泰山轴", 86), ("磁玉pro", 2), ("万磁王", 5)]:
        assert cli.main(prefix + ["switch-type", name, "1"]) == 0
        capsys.readouterr()
        assert fw.fields[252][1] == code
    assert cli.main(prefix + ["magnetic-key", "1", "--travel", "3.3"]) == 0
    capsys.readouterr()
    assert fw.fields[0][2:4] == (660).to_bytes(2, "little")
    hidden = fw.sleep[3]
    assert cli.main(prefix + ["sleep", "60", "3600", "600"]) == 0
    capsys.readouterr()
    assert fw.sleep == [60, 3600, 600, hidden]


@pytest.mark.parametrize(
    "command",
    [
        ["profile", "2"],
        ["switch-type", "灭霸轴", "1"],
        ["switch-type", "白星", "1"],
        ["magnetic-key", "1", "--travel", "2.005"],
        ["sleep", "0", "60", "600"],
        ["sleep", "60", "60", "599"],
        ["sleep", "60", "60", "600", "600"],
        ["debounce", "3"],
    ],
)
def test_tmr3613_cli_rejects_other_variants_features(monkeypatch, capsys, command):
    _, fw, info = install(monkeypatch, 3613)
    assert cli.main(["--device", info.path] + command) == 1
    assert "error" in capsys.readouterr().err
    assert not fw.sent
