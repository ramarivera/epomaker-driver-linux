import threading
import time

import pytest

from epomaker_driver.audio_capture import AudioCaptureError
from epomaker_driver.audio_preview import AudioPreview

FRAME = [0.0] * 512


class FakeCapture:
    instances = []
    close_error = None

    def __init__(self, **kwargs):
        self.stop_event = kwargs["stop_event"]
        self.closed = False
        self.started = threading.Event()
        self.__class__.instances.append(self)

    def __enter__(self):
        self.started.set()
        return self

    def __exit__(self, *_):
        self.closed = True
        if self.close_error:
            raise self.close_error

    def close(self):
        self.closed = True
        if self.close_error:
            raise self.close_error

    def read_samples(self):
        self.started.set()
        while not self.stop_event.wait(0.01):
            return FRAME
        raise AudioCaptureError("audio capture stopped")


@pytest.fixture(autouse=True)
def reset_captures():
    FakeCapture.instances.clear()
    FakeCapture.close_error = None


def wait_until(predicate):
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    assert predicate()


def test_samples_status_and_reuse():
    preview = AudioPreview(FakeCapture)
    first = preview.start()
    wait_until(lambda: preview.status()["sequence"] > 0)
    status = preview.sample(first["session"])
    assert status["sequence"] > 0
    bands = status["bands"]
    bands[0] = 99
    assert preview.status()["bands"][0] != 99
    preview.stop(first["session"])
    second = preview.start()
    assert second["session"] != first["session"]
    preview.stop()


def test_duplicate_start_and_stale_stop_are_harmless():
    preview = AudioPreview(FakeCapture)
    token = preview.start()["session"]
    with pytest.raises(ValueError):
        preview.start()
    assert preview.stop("stale") == {"ok": True, "error": None}
    with pytest.raises(ValueError):
        preview.sample("stale")
    assert preview.status()["running"]
    preview.stop(token)


def test_invalid_settings_do_not_construct_capture():
    with pytest.raises(ValueError):
        AudioPreview(FakeCapture, lease=0)
    assert not FakeCapture.instances


def test_invalid_analysis_settings_are_checked_before_capture():
    preview = AudioPreview(FakeCapture)
    with pytest.raises((ValueError, TypeError)):
        preview.start(unsupported=True)
    assert not FakeCapture.instances


def test_invalid_clock_is_rejected():
    with pytest.raises(ValueError, match="clock"):
        AudioPreview(FakeCapture, clock=object())


def test_sample_after_worker_failure_returns_error_status():
    class Broken(FakeCapture):
        def read_samples(self):
            raise RuntimeError("worker failed")

    preview = AudioPreview(Broken)
    token = preview.start()["session"]
    wait_until(lambda: not preview.status()["running"])
    assert preview.sample(token)["error"] == "worker failed"


def test_restart_waits_for_previous_worker_context_to_close():
    class SlowClose(FakeCapture):
        def read_samples(self):
            raise RuntimeError("finished")

    preview = AudioPreview(SlowClose)
    first = preview.start()["session"]
    wait_until(lambda: not preview.status()["running"])
    second = preview.start()["session"]
    assert second != first
    assert FakeCapture.instances[0].closed
    preview.stop()


@pytest.mark.parametrize("close_error", [None, RuntimeError("close failed")])
def test_thread_start_failure_closes_capture_and_clears_thread(monkeypatch, close_error):
    FakeCapture.close_error = close_error

    def fail_start(_):
        raise RuntimeError("thread failed")

    monkeypatch.setattr(threading.Thread, "start", fail_start)
    preview = AudioPreview(FakeCapture)
    with pytest.raises(RuntimeError, match="thread failed"):
        preview.start()
    assert preview.thread is None
    assert not preview.status()["running"]
    assert FakeCapture.instances[0].closed
    assert preview.status()["error"] == (None if close_error is None else "close failed")


def test_capture_error_and_eof_are_reported():
    class Broken(FakeCapture):
        def read_samples(self):
            raise RuntimeError("EOF")

    preview = AudioPreview(Broken)
    preview.start()
    wait_until(lambda: not preview.status()["running"])
    assert preview.status()["error"] == "EOF"


def test_lease_expiry_stops_capture_and_sample_extends_lease():
    now = [0.0]
    preview = AudioPreview(FakeCapture, clock=lambda: now[0], lease=5)
    token = preview.start()["session"]
    now[0] = 4
    preview.sample(token)
    now[0] = 10
    wait_until(lambda: not preview.status()["running"])
    assert "browser stopped polling" in preview.status()["error"]
    assert FakeCapture.instances[0].closed


def test_close_failure_is_returned_and_preserved_on_explicit_stop():
    FakeCapture.close_error = RuntimeError("close failed")
    preview = AudioPreview(FakeCapture)
    token = preview.start()["session"]
    result = preview.stop(token)
    assert result == {"ok": False, "error": "close failed"}
    assert preview.status()["error"] == "close failed"
