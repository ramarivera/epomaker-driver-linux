import threading

import pytest

from epomaker_driver import browser_launch, cli, server


def test_browser_open_is_background_and_uses_new_tab(monkeypatch):
    release = threading.Event()
    started = threading.Event()
    calls = []

    def open(url, new):
        calls.append((url, new))
        started.set()
        release.wait(2)
        return True

    monkeypatch.setattr(browser_launch.webbrowser, "open", open)
    worker = browser_launch.open_browser("http://127.0.0.1:1234/#token=test")
    try:
        assert started.wait(1)
        assert worker.is_alive() and worker.daemon
        assert calls == [("http://127.0.0.1:1234/#token=test", 2)]
    finally:
        release.set()
        worker.join(2)


@pytest.mark.parametrize("fails", [False, True])
def test_browser_failure_reports_manual_fallback(monkeypatch, capsys, fails):
    def open(*args, **kwargs):
        if fails:
            raise OSError("browser unavailable")
        return False

    monkeypatch.setattr(browser_launch.webbrowser, "open", open)
    worker = browser_launch.open_browser("http://127.0.0.1:1234/#token=test")
    worker.join(2)
    assert "session URL manually" in capsys.readouterr().err


def test_serve_browser_open_is_explicit_and_uses_actual_port(monkeypatch, capsys):
    opened = []
    monkeypatch.setattr(browser_launch, "open_browser", opened.append)
    monkeypatch.setattr(server.ControlServer, "serve_forever", lambda _: None)
    assert cli.main(["serve", "--port", "0"]) == 0
    assert not opened
    capsys.readouterr()
    assert cli.main(["serve", "--port", "0", "--open-browser"]) == 0
    assert opened == [capsys.readouterr().out.splitlines()[0]]
    assert opened[0].startswith("http://127.0.0.1:") and ":0/" not in opened[0]
