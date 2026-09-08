"""G84 HE Pro CLI dispatch uses its exact switch and feature gates."""

import json

import pytest
from test_he_recovery_cli import install

from epomaker_driver import cli


def test_g84_cli_profiles_switch_sleep_and_magnetic_edit(monkeypatch, capsys):
    _, fw, info = install(monkeypatch, 4071)
    prefix = ["--device", info.path]
    assert cli.main(prefix + ["identify"]) == 0
    assert json.loads(capsys.readouterr().out)["device_id"] == 4071
    assert cli.main(prefix + ["profile", "3"]) == 0
    capsys.readouterr()
    assert cli.main(prefix + ["switch-type", "海木比目鱼轴", "1"]) == 0
    capsys.readouterr()
    assert fw.fields[252][1] == 133
    hidden = fw.sleep[3]
    assert cli.main(prefix + ["sleep", "60", "3600", "600"]) == 0
    capsys.readouterr()
    assert fw.sleep == [60, 3600, 600, hidden]
    assert cli.main(prefix + ["magnetic-key", "1", "--travel", "3.3", "--deadzone", "1"]) == 0
    capsys.readouterr()
    assert fw.fields[0][2:4] == (660).to_bytes(2, "little")
    assert fw.fields[6][2:4] == (200).to_bytes(2, "little")


@pytest.mark.parametrize(
    "command",
    [
        ["switch-type", "高特", "1"],
        ["switch-type", "云玉磁轴", "1"],
        ["sleep", "0", "60", "600"],
        ["sleep", "60", "60", "599"],
        ["magnetic-key", "1", "--travel", "3.305"],
        ["magnetic-key", "1", "--deadzone", "1.005"],
        ["get-light", "--side"],
        ["debounce", "3"],
    ],
)
def test_g84_cli_rejects_unadvertised_or_outside_catalog_values(monkeypatch, capsys, command):
    _, fw, info = install(monkeypatch, 4071)
    assert cli.main(["--device", info.path] + command) == 1
    assert "error" in capsys.readouterr().err
    assert not fw.sent
