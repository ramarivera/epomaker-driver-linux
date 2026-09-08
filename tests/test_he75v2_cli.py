"""HE75 V2 USB routing, profile counts, switch labels and timer bounds."""

import json

import pytest
from test_he_recovery_cli import install

from epomaker_driver import cli


@pytest.mark.parametrize("model,profile,up", [(3518, 1, 91), (3883, 3, 96)])
def test_he75_cli_identity_profiles_knob_and_switch(model, profile, up, monkeypatch, capsys):
    _, fw, info = install(monkeypatch, model)
    prefix = ["--device", info.path]
    assert cli.main(prefix + ["identify"]) == 0
    assert json.loads(capsys.readouterr().out)["device_id"] == model
    assert cli.main(prefix + ["profile", str(profile)]) == 0
    capsys.readouterr()
    assert fw.profile == profile
    assert cli.main(prefix + ["bind-media", str(up), "volume-up", "--profile", str(profile)]) == 0
    capsys.readouterr()
    assert fw.matrices[profile, 0][up * 4 : up * 4 + 4] == bytes.fromhex("0300e900")
    assert cli.main(prefix + ["switch-type", "灭霸轴", "1"]) == 0
    capsys.readouterr()
    assert fw.fields[252][1] == 43


@pytest.mark.parametrize("model,values", [(3518, [60, 3600, 600]), (3883, [0, 65535, 0])])
def test_he75_cli_catalog_sleep_limits(model, values, monkeypatch, capsys):
    _, fw, info = install(monkeypatch, model)
    hidden = fw.sleep[3]
    assert cli.main(["--device", info.path, "sleep", *map(str, values)]) == 0
    capsys.readouterr()
    assert fw.sleep == values + [hidden]


@pytest.mark.parametrize(
    "model,command",
    [
        (3518, ["profile", "2"]),
        (3518, ["sleep", "0", "60", "600"]),
        (3518, ["sleep", "60", "60", "599"]),
        (3883, ["sleep", "0", "65536", "0"]),
        (3883, ["magnetic-key", "1", "--travel", "2.005"]),
        (3883, ["switch-type", "白星", "1"]),
        (3518, ["key", "90", "09020000"]),
        (3883, ["key", "96", "00000400", "--fn"]),
        (3883, ["magnetic-key", "97", "--travel", "2"]),
    ],
)
def test_he75_cli_model_restrictions_prevent_writes(model, command, monkeypatch, capsys):
    _, fw, info = install(monkeypatch, model)
    assert cli.main(["--device", info.path] + command) == 1
    assert "error" in capsys.readouterr().err
    assert not fw.sent


def test_display_alias_is_not_a_second_wire_switch_name(monkeypatch, capsys):
    _, fw, info = install(monkeypatch, 3518)
    with pytest.raises(SystemExit) as error:
        cli.main(["--device", info.path, "switch-type", "紫星轴", "1"])
    assert error.value.code == 2
    assert "invalid" in capsys.readouterr().err
    assert not fw.sent
