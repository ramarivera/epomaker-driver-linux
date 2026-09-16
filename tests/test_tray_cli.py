import sys
from types import SimpleNamespace

from epomaker_driver import cli, server, user_service
from epomaker_driver.errors import DriverError


def test_serve_tray_callbacks_and_cleanup(tmp_path, monkeypatch, capsys):
    events = []

    class FakeTray:
        def __init__(self, open_callback, quit_callback):
            self.open, self.quit = open_callback, quit_callback

        def __enter__(self):
            events.append("tray started")
            self.open()
            self.quit()
            return self

        def __exit__(self, *_):
            events.append("tray stopped")

    monkeypatch.setitem(sys.modules, "epomaker_driver.tray", SimpleNamespace(Tray=FakeTray))
    monkeypatch.setattr(cli.browser_launch, "open_browser", lambda url, **kw: events.append(url))
    monkeypatch.setattr(server.ControlServer, "shutdown", lambda self: events.append("quit"))
    monkeypatch.setattr(server.ControlServer, "serve_forever", lambda self: events.append("serve"))
    assert cli.main(["serve", "--tray", "--port", "0", "--backup-dir", str(tmp_path)]) == 0
    assert events[0] == "tray started"
    assert events[1].startswith("http://127.0.0.1:") and "#token=" in events[1]
    assert events[2:] == ["quit", "serve", "tray stopped"]
    assert "stopped" in capsys.readouterr().out


def test_tray_failure_closes_server_without_starting_http_loop(tmp_path, monkeypatch, capsys):
    events = []

    class FailedTray:
        def __init__(self, *_):
            pass

        def __enter__(self):
            raise DriverError("No StatusNotifier tray host")

        def __exit__(self, *_):
            pass

    monkeypatch.setitem(sys.modules, "epomaker_driver.tray", SimpleNamespace(Tray=FailedTray))
    monkeypatch.setattr(server.Controller, "close", lambda self: events.append("closed"))
    monkeypatch.setattr(server.ControlServer, "serve_forever", lambda self: events.append("serve"))
    assert cli.main(["serve", "--tray", "--port", "0", "--backup-dir", str(tmp_path)]) == 1
    assert events == ["closed"]
    captured = capsys.readouterr()
    assert "tray host" in captured.err and "#token=" not in captured.out


def test_service_install_forwards_tray_option(tmp_path, monkeypatch, capsys):
    values = []
    monkeypatch.setattr(user_service, "install", lambda home, exe, **kw: values.append(kw) or {})
    assert cli.main(["service-install", "--tray", "--config-home", str(tmp_path)]) == 0
    assert values == [{"tray": True}]
