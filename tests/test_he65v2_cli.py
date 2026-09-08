"""HE65 V2 two-timer CLI and ordinary knob key bindings."""

import json

import pytest
from test_he_recovery_cli import install

from epomaker_driver import cli


def test_he65_cli_two_timers_preserve_both_hidden_words(monkeypatch, capsys):
    _, fw, info = install(monkeypatch, 3417)
    fw.sleep = [120, 120, 0xCAFE, 0xBEEF]
    prefix = ["--device", info.path]
    assert cli.main(prefix + ["sleep", "0", "64800"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert "deep_bluetooth" not in result and "deep_dongle" not in result
    assert fw.sleep == [0, 64800, 0xCAFE, 0xBEEF]
    assert cli.main(prefix + ["get-sleep"]) == 0
    assert "deep_bluetooth" not in json.loads(capsys.readouterr().out)


def test_he65_cli_knob_bindings_and_switch_codes(monkeypatch, capsys):
    _, fw, info = install(monkeypatch, 3417)
    prefix = ["--device", info.path]
    for name, slot, code in [("volume-up", 90, 233), ("volume-down", 91, 234), ("mute", 92, 226)]:
        assert cli.main(prefix + ["bind-media", str(slot), name, "--profile", "3"]) == 0
        capsys.readouterr()
        assert fw.matrices[3, 0][slot * 4 : slot * 4 + 4] == bytes([3, 0, code, 0])
    for name, code in [("机械轴", 7), ("云玉磁轴", 93)]:
        assert cli.main(prefix + ["switch-type", name, "1"]) == 0
        capsys.readouterr()
        assert fw.fields[252][1] == code


@pytest.mark.parametrize(
    "command",
    [
        ["sleep", "0", "0", "600"],
        ["sleep", "0", "64801"],
        ["sleep", "-1", "0"],
        ["magnetic-key", "90", "--travel", "2"],
        ["switch-type", "机械轴", "91"],
        ["key", "92", "00000400", "--fn"],
        ["key", "90", "09020000"],
        ["get-light", "--side"],
    ],
)
def test_he65_cli_rejects_unexposed_controls_before_writes(monkeypatch, capsys, command):
    _, fw, info = install(monkeypatch, 3417)
    assert cli.main(["--device", info.path] + command) == 1
    assert "error" in capsys.readouterr().err
    assert not fw.sent


@pytest.mark.parametrize("model", [3727, 3759, 3365, 4071, 3692])
def test_two_sleep_arguments_do_not_relax_other_models(monkeypatch, capsys, model):
    _, fw, info = install(monkeypatch, model)
    assert cli.main(["--device", info.path, "sleep", "60", "60"]) == 1
    assert "error" in capsys.readouterr().err
    assert not fw.sent
