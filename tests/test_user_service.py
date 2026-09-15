import pytest

from epomaker_driver import user_service


def exe(tmp_path):
    value = tmp_path / "py space $value %value"
    value.write_text("python")
    value.chmod(0o755)
    return value


def test_install_and_uninstall_are_atomic_and_owned(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(user_service, "_systemctl", lambda action: calls.append(action))
    home = tmp_path / "config"
    result = user_service.install(home, exe(tmp_path))
    path = home / "systemd/user" / user_service.UNIT
    assert result["installed"] and path.exists()
    text = path.read_text()
    assert user_service.MARKER in text
    assert "RuntimeDirectoryMode=0700" in text
    assert "StandardOutput=null" in text
    assert 'ExecStart="' in text
    assert calls == ["daemon-reload"]
    assert user_service.uninstall(home)["removed"] is True
    assert calls == ["daemon-reload", "stop", "daemon-reload"]


def test_refuses_unrelated_and_symlink_unit(tmp_path, monkeypatch):
    monkeypatch.setattr(user_service, "_systemctl", lambda action: None)
    home = tmp_path / "config"
    path = home / "systemd/user" / user_service.UNIT
    path.parent.mkdir(parents=True)
    path.write_text("[Service]\nExecStart=someone-else\n")
    with pytest.raises(ValueError):
        user_service.install(home, exe(tmp_path))
    path.unlink()
    target = tmp_path / "target"
    target.write_text("safe")
    path.symlink_to(target)
    with pytest.raises(ValueError):
        user_service.uninstall(home)


def test_control_uses_user_systemd_and_parses_status(monkeypatch):
    seen = []

    class Result:
        stdout = "LoadState=loaded\nActiveState=active\nSubState=running\n"

    def fake(action):
        seen.append(action)
        return Result()

    monkeypatch.setattr(user_service, "_systemctl", fake)
    assert user_service.control("start")["ok"]
    status = user_service.control("status")
    assert status["ActiveState"] == "active"
    assert seen == ["start", "status"]
    with pytest.raises(ValueError):
        user_service.control("enable")


def test_rejects_bad_paths_and_daemon_reload_failure(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        user_service.install(tmp_path / "config", tmp_path / "missing")
    monkeypatch.setattr(
        user_service,
        "_systemctl",
        lambda action: (_ for _ in ()).throw(user_service.ServiceError("no systemd")),
    )
    with pytest.raises(user_service.ServiceError):
        user_service.install(tmp_path / "config", exe(tmp_path))
    assert (tmp_path / "config/systemd/user" / user_service.UNIT).exists()


def test_systemctl_status_uses_show_and_error_is_actionable(monkeypatch):
    import subprocess

    seen = []

    def run(command, **kwargs):
        seen.append((command, kwargs))
        return subprocess.CompletedProcess(
            command, 0, "LoadState=loaded\nActiveState=inactive\nSubState=dead\n"
        )

    monkeypatch.setattr(user_service.subprocess, "run", run)
    assert user_service.control("status")["ActiveState"] == "inactive"
    assert seen[0][0] == [
        "systemctl",
        "--user",
        "show",
        "--property=LoadState,ActiveState,SubState",
        user_service.UNIT,
    ]
    assert seen[0][1]["check"] and seen[0][1]["timeout"] == 10
    monkeypatch.setattr(
        user_service.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError())
    )
    with pytest.raises(user_service.ServiceError, match="user session"):
        user_service.control("start")


@pytest.mark.parametrize("name", ['py"quote', "py'quote", "py\\slash", "py\nnewline", "py\tvalue"])
def test_unsupported_executable_characters_rejected(tmp_path, monkeypatch, name):
    executable = tmp_path / name
    executable.write_text("python")
    executable.chmod(0o755)
    monkeypatch.setattr(
        user_service, "_systemctl", lambda _: pytest.fail("must validate before reload")
    )
    with pytest.raises(ValueError):
        user_service.install(tmp_path / "config", executable)
    assert not (tmp_path / "config/systemd/user" / user_service.UNIT).exists()


def test_update_preserves_unit_on_reload_failure_and_uninstall_stop_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(user_service, "_systemctl", lambda _: None)
    home = tmp_path / "config"
    executable = exe(tmp_path)
    user_service.install(home, executable)
    path = home / "systemd/user" / user_service.UNIT
    monkeypatch.setattr(
        user_service,
        "_systemctl",
        lambda _: (_ for _ in ()).throw(user_service.ServiceError("failed")),
    )
    with pytest.raises(user_service.ServiceError, match="unit saved"):
        user_service.install(home, executable)
    assert path.exists()
    with pytest.raises(user_service.ServiceError):
        user_service.uninstall(home)
    assert path.exists()


def test_cli_service_routing(tmp_path, monkeypatch, capsys):
    from epomaker_driver import cli

    seen = []
    monkeypatch.setattr(
        user_service, "install", lambda home, executable: seen.append((home, executable)) or {}
    )
    monkeypatch.setattr(user_service, "uninstall", lambda home: seen.append(home) or {})
    monkeypatch.setattr(user_service, "control", lambda action: {"action": action})
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert cli.main(["service-install"]) == 0
    assert seen[0][0] == tmp_path
    assert cli.main(["service-uninstall", "--config-home", str(tmp_path)]) == 0
    assert seen[1] == tmp_path
    for action in ("start", "stop", "status"):
        assert cli.main(["service-" + action]) == 0
    assert capsys.readouterr().out
