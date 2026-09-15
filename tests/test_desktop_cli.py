import json
from pathlib import Path

from epomaker_driver import cli, desktop


def test_xdg_launcher_lifecycle_never_discovers_hardware(tmp_path, monkeypatch, capsys):
    data_home = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setattr(
        cli, "select_device", lambda _: (_ for _ in ()).throw(AssertionError("offline"))
    )
    assert cli.main(["desktop-status"]) == 0
    assert json.loads(capsys.readouterr().out)["installed"] is False
    assert cli.main(["desktop-install"]) == 0
    installed = json.loads(capsys.readouterr().out)
    assert Path(installed["path"]).is_file()
    preserved = data_home / "epomaker-driver-linux/macros/keep.json"
    preserved.parent.mkdir(parents=True)
    preserved.write_text("library")
    assert cli.main(["desktop-status"]) == 0
    assert json.loads(capsys.readouterr().out)["installed"] is True
    assert cli.main(["desktop-uninstall"]) == 0
    assert json.loads(capsys.readouterr().out)["removed"] is True
    assert preserved.read_text() == "library"


def test_explicit_data_home_and_relative_xdg_rejected(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_DATA_HOME", "relative")
    assert cli.main(["desktop-status"]) == 1
    assert "absolute path" in capsys.readouterr().err
    assert cli.main(["desktop-install", "--data-home", str(tmp_path)]) == 0
    assert (tmp_path / "applications" / desktop.FILENAME).is_file()


def test_default_data_home(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert cli.main(["desktop-status"]) == 0
    assert json.loads(capsys.readouterr().out)["path"] == str(
        tmp_path / ".local/share/applications" / desktop.FILENAME
    )
