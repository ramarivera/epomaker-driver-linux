"""HE108 USB CLI dispatch, including its narrower catalog sleep ranges."""

import json

import pytest
from test_he_recovery_cli import install

from epomaker_driver import cli


def test_he108_cli_model_sleep_side_and_profile(monkeypatch, capsys):
    kb, fw, info = install(monkeypatch, 3365)
    prefix = ["--device", info.path]
    assert cli.main(prefix + ["identify"]) == 0
    assert json.loads(capsys.readouterr().out)["device_id"] == 3365
    assert cli.main(prefix + ["profile", "3"]) == 0
    capsys.readouterr()
    assert fw.profile == 3
    hidden = fw.sleep[3]
    assert cli.main(prefix + ["sleep", "60", "3600", "600"]) == 0
    capsys.readouterr()
    assert fw.sleep == [60, 3600, 600, hidden]
    assert cli.main(prefix + ["light", "wave", "--side", "--speed", "3"]) == 0
    capsys.readouterr()
    assert any(c[0] == 8 for c in fw.sent)
    assert cli.main(prefix + ["switch-type", "万磁王", "1"]) == 0
    capsys.readouterr()
    assert fw.fields[252][1] == 5


@pytest.mark.parametrize(
    "args",
    [
        ["sleep", "59", "60", "600"],
        ["sleep", "60", "3601", "600"],
        ["sleep", "60", "60", "599"],
        ["sleep", "60", "60", "3601"],
        ["sleep", "60", "60", "600", "600"],
        ["debounce", "3"],
        ["switch-type", "云玉磁轴", "1"],
    ],
)
def test_he108_cli_invalid_values_do_not_write(monkeypatch, capsys, args):
    _, fw, info = install(monkeypatch, 3365)
    assert cli.main(["--device", info.path] + args) == 1
    assert "error" in capsys.readouterr().err
    assert not fw.sent
