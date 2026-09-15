from pathlib import Path

import pytest

from epomaker_driver import cli, control_socket, user_service

URL = "http://127.0.0.1:12345/#token=" + "a" * 32


def test_start_waits_for_socket_without_restarting(monkeypatch, tmp_path):
    starts, reads = [], []
    monkeypatch.setattr(user_service, "control", starts.append)
    monkeypatch.setattr(user_service.time, "sleep", lambda _: None)

    def read(path):
        reads.append(path)
        if len(reads) < 3:
            raise FileNotFoundError()
        return URL

    monkeypatch.setattr(control_socket, "read_url", read)
    assert user_service.activate(tmp_path) == URL
    assert starts == ["start"]
    assert reads == [tmp_path / "epomaker-driver-linux/control.sock"] * 3


def test_activation_failure_timeout_and_validation(monkeypatch, tmp_path):
    starts = []
    monkeypatch.setattr(user_service, "control", starts.append)
    with pytest.raises(ValueError):
        user_service.activate(Path("relative"))
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError):
        user_service.activate(tmp_path)
    assert not starts
    tmp_path.chmod(0o700)
    monkeypatch.setattr(user_service, "READY_TIMEOUT", 0)
    monkeypatch.setattr(
        control_socket, "read_url", lambda _: (_ for _ in ()).throw(ConnectionRefusedError())
    )
    with pytest.raises(user_service.ServiceError, match="timed out"):
        user_service.activate(tmp_path)
    assert starts == ["start"]


def test_bad_socket_is_not_silently_retried(monkeypatch, tmp_path):
    monkeypatch.setattr(user_service, "control", lambda _: None)
    monkeypatch.setattr(
        control_socket, "read_url", lambda _: (_ for _ in ()).throw(ValueError("not private"))
    )
    with pytest.raises(ValueError, match="not private"):
        user_service.activate(tmp_path)


def test_start_failure_does_not_use_old_socket(monkeypatch, tmp_path):
    monkeypatch.setattr(
        user_service,
        "control",
        lambda _: (_ for _ in ()).throw(user_service.ServiceError("start failed")),
    )
    monkeypatch.setattr(
        control_socket, "read_url", lambda _: pytest.fail("must not open stale service")
    )
    with pytest.raises(user_service.ServiceError, match="start failed"):
        user_service.activate(tmp_path)


@pytest.mark.parametrize("browser_failure", [False, True])
def test_menu_activation_does_not_print_token(monkeypatch, tmp_path, capsys, browser_failure):
    requested = []
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(user_service, "activate", lambda path: requested.append(path) or URL)

    def open_browser(url, new):
        if browser_failure:
            raise OSError("could not launch " + url)
        return True

    monkeypatch.setattr(cli.browser_launch.webbrowser, "open", open_browser)
    assert cli.main(["service-launch"]) == 0
    output = capsys.readouterr()
    assert URL not in output.out + output.err
    assert "token=" not in output.out + output.err
    assert requested == [tmp_path]
    if browser_failure:
        assert "service-open" in output.err


def test_menu_activation_requires_session(monkeypatch, capsys):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(
        user_service, "activate", lambda _: pytest.fail("must validate session first")
    )
    assert cli.main(["service-launch"]) == 1
    assert "XDG_RUNTIME_DIR" in capsys.readouterr().err


def test_login_startup_controls_do_not_implicitly_start(monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(user_service, "_systemctl", seen.append)
    assert cli.main(["service-enable"]) == 0
    assert cli.main(["service-disable"]) == 0
    assert seen == ["enable", "disable"]
    assert capsys.readouterr().out


def test_background_launcher_flag(tmp_path, capsys):
    assert cli.main(["desktop-install", "--background", "--data-home", str(tmp_path)]) == 0
    entry = (tmp_path / "applications" / cli.desktop.FILENAME).read_text()
    assert "Terminal=false" in entry and "service-launch" in entry
    assert "token" not in entry
    assert capsys.readouterr().out


def test_repeated_activation_reads_same_running_socket(monkeypatch):
    import tempfile

    starts = []
    monkeypatch.setattr(user_service, "control", starts.append)
    with tempfile.TemporaryDirectory(prefix="epo-menu-") as directory:
        runtime = Path(directory)
        with control_socket.ControlSocket(runtime / "epomaker-driver-linux/control.sock", URL):
            assert user_service.activate(runtime) == URL
            assert user_service.activate(runtime) == URL
    assert starts == ["start", "start"]  # Both requests target the same fixed systemd unit.
