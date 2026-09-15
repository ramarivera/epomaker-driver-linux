import os
import socket

import pytest

from epomaker_driver import cli, control_socket, server

URL = "http://127.0.0.1:12345/#token=" + "a" * 32


@pytest.fixture
def path(tmp_path):
    # Unix socket names have a small kernel limit; pytest's nested names can exceed it.
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory(prefix="epo-") as directory:
        yield Path(directory) / "control.sock"


def test_live_url_is_private_and_cleanup_removes_only_socket(path):
    with control_socket.ControlSocket(path, URL):
        assert path.stat().st_mode & 0o777 == 0o600
        assert control_socket.read_url(path) == URL
        assert control_socket.read_url(path) == URL
        assert list(path.parent.iterdir()) == [path]
    assert not path.exists()


def test_existing_file_or_live_socket_is_preserved(path):
    path.write_text("other data")
    with pytest.raises(OSError):
        control_socket.ControlSocket(path, URL)
    assert path.read_text() == "other data"
    path.unlink()
    with control_socket.ControlSocket(path, URL):
        with pytest.raises(OSError):
            control_socket.ControlSocket(path, URL)
        assert control_socket.read_url(path) == URL


def test_permissions_and_nonlocal_urls_rejected(path):
    path.parent.chmod(0o755)
    with pytest.raises(ValueError, match="0700"):
        control_socket.ControlSocket(path, URL)
    path.parent.chmod(0o700)
    with pytest.raises(ValueError):
        control_socket.ControlSocket(path, "https://example.com/#token=" + "a" * 32)
    with pytest.raises(ValueError):
        control_socket.ControlSocket("relative.sock", URL)
    with pytest.raises(ValueError):
        control_socket.read_url("relative.sock")
    with control_socket.ControlSocket(path, URL):
        path.chmod(0o666)
        with pytest.raises(ValueError):
            control_socket.read_url(path)


def test_symlink_reader_rejected(path):
    from pathlib import Path

    target = Path(str(path) + ".target")
    target.write_text("not a socket")
    path.symlink_to(target)
    with pytest.raises(ValueError):
        control_socket.read_url(path)


def test_read_rejects_nonlocal_server_response(path):
    import threading

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.bind(str(path))
        os.chmod(path, 0o600)
        sock.listen()

        def serve():
            client, _ = sock.accept()
            with client:
                client.sendall(b"https://example.com")

        thread = threading.Thread(target=serve)
        thread.start()
        with pytest.raises(ValueError):
            control_socket.read_url(path)
        thread.join()


def test_cli_serve_publishes_url_without_stdout_token(path, monkeypatch, capsys):
    found = []
    monkeypatch.setattr(
        server.ControlServer, "serve_forever", lambda _: found.append(control_socket.read_url(path))
    )
    assert cli.main(["serve", "--port", "0", "--control-socket", str(path)]) == 0
    assert found[0].startswith("http://127.0.0.1:")
    assert "token" not in capsys.readouterr().out
    assert not path.exists()


def test_cli_service_open_uses_runtime_socket(path, monkeypatch, capsys):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    assert cli.main(["service-open"]) == 1
    assert "XDG_RUNTIME_DIR" in capsys.readouterr().err
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(path.parent))
    target = path.parent / "epomaker-driver-linux/control.sock"
    opened = []
    monkeypatch.setattr(
        cli.browser_launch.webbrowser, "open", lambda url, new: opened.append(url) or True
    )
    with control_socket.ControlSocket(target, URL):
        assert cli.main(["service-open"]) == 0
    assert opened == [URL]
    assert URL in capsys.readouterr().out
