import os
import struct
import subprocess
import threading
import time

import pytest

from epomaker_driver.audio_capture import AudioCaptureError, PipeWireCapture


class FakeProcess:
    def __init__(self, payload=b"", *, exit_code=None, read_size=None):
        read_fd, write_fd = os.pipe()
        self.stdout = os.fdopen(read_fd, "rb")
        self.stderr = None
        self._exit_code = exit_code
        self._final = exit_code
        self.read_size = read_size
        os.write(write_fd, payload)
        os.close(write_fd)

    def poll(self):
        return self._exit_code

    def wait(self, timeout=None):
        self._exit_code = 0 if self._final is None else self._final
        return self._exit_code

    def terminate(self):
        self._exit_code = 0

    def kill(self):
        self._exit_code = -9


class OpenPipeProcess(FakeProcess):
    def __init__(self):
        read_fd, self.write_fd = os.pipe()
        self.stdout = os.fdopen(read_fd, "rb")
        self.stderr = None
        self._exit_code = None
        self._final = 0

    def finish(self):
        os.close(self.write_fd)
        self.write_fd = None
        self._exit_code = self._final


def factory_for(payload=b"", exit_code=None):
    calls = []

    def factory(argv, **kwargs):
        calls.append((argv, kwargs))
        return FakeProcess(payload, exit_code=exit_code)

    factory.calls = calls
    return factory


def test_pw_cat_argv_and_partial_sample_reads():
    factory = factory_for(struct.pack("<3f", -1.0, 0.25, 1.0))
    with PipeWireCapture(process_factory=factory, chunk_samples=3) as capture:
        assert capture.read_samples() == [-1.0, 0.25, 1.0]
    argv, kwargs = factory.calls[0]
    assert argv == [
        "pw-cat",
        "--record",
        "--raw",
        "--format",
        "f32",
        "--rate",
        "48000",
        "--channels",
        "1",
        "--properties",
        '{"stream.capture.sink":true}',
        "--target",
        "auto",
        "-",
    ]
    assert kwargs["stderr"] is not None


def test_target_validation_and_timeout_stop_and_nonfinite():
    for target in ("", "bad\x00target", None):
        with pytest.raises(ValueError):
            PipeWireCapture(target=target)
    with pytest.raises(ValueError):
        PipeWireCapture(read_timeout=float("inf"))
    with pytest.raises(ValueError):
        PipeWireCapture(chunk_samples=0)
    capture = PipeWireCapture(process_factory=factory_for(), read_timeout=0.01)
    with capture:
        with pytest.raises(AudioCaptureError, match="timed out|exited|closed"):
            capture.read_samples(1)
    capture = PipeWireCapture(process_factory=factory_for(struct.pack("<f", float("nan"))))
    with capture:
        with pytest.raises(AudioCaptureError, match="non-finite"):
            capture.read_samples(1)


def test_nonzero_exit_and_close_are_actionable_and_idempotent():
    factory = factory_for(exit_code=7)
    capture = PipeWireCapture(process_factory=factory)
    with capture:
        with pytest.raises(AudioCaptureError, match="status 7"):
            capture.read_samples(1)
    capture.close()
    capture.close()


def test_missing_dependency_is_actionable():
    def missing(argv, **kwargs):
        raise FileNotFoundError

    with pytest.raises(AudioCaptureError, match="not installed"):
        with PipeWireCapture(process_factory=missing):
            pass


def test_stop_event_interrupts_silent_capture():
    event = threading.Event()
    process = OpenPipeProcess()
    capture = PipeWireCapture(
        process_factory=lambda *args, **kwargs: process, stop_event=event, read_timeout=1
    )
    with capture:
        setter = threading.Timer(0.02, event.set)
        setter.start()
        with pytest.raises(AudioCaptureError, match="stopped"):
            capture.read_samples(1)
        setter.join()


def test_delayed_partial_pipe_read_does_not_block():
    process = OpenPipeProcess()

    def writer():
        os.write(process.write_fd, struct.pack("=f", 0.25)[:2])
        time.sleep(0.03)
        os.write(process.write_fd, struct.pack("=f", 0.25)[2:])
        process.finish()

    thread = threading.Thread(target=writer)
    thread.start()
    capture = PipeWireCapture(process_factory=lambda *args, **kwargs: process, chunk_samples=1)
    with capture:
        assert capture.read_samples(1) == [0.25]
    thread.join()


def test_read_deadline_is_bounded_and_eof_without_exit_is_error():
    process = OpenPipeProcess()
    capture = PipeWireCapture(process_factory=lambda *args, **kwargs: process, read_timeout=0.12)
    with capture:
        started = time.monotonic()
        with pytest.raises(AudioCaptureError, match="timed out"):
            capture.read_samples(1)
        assert time.monotonic() - started < 0.35
        process.finish()
    process = OpenPipeProcess()
    capture = PipeWireCapture(process_factory=lambda *args, **kwargs: process)
    with capture:
        os.close(process.write_fd)
        process.write_fd = None
        with pytest.raises(AudioCaptureError, match="closed its output"):
            capture.read_samples(1)


def test_registration_failure_cleans_up_process(monkeypatch):
    process = FakeProcess()

    class BrokenSelector:
        def register(self, *_args):
            raise OSError("register failed")

        def close(self):
            pass

    monkeypatch.setattr("epomaker_driver.audio_capture.selectors.DefaultSelector", BrokenSelector)
    capture = PipeWireCapture(process_factory=lambda *args, **kwargs: process)
    with pytest.raises(AudioCaptureError, match="monitor"):
        capture.__enter__()
    assert capture.process is None
    assert process.poll() == 0


def test_close_kills_process_after_terminate_timeout():
    process = FakeProcess()
    process._exit_code = None
    process.terminate = lambda: None
    waits = []

    def wait(timeout=None):
        waits.append(timeout)
        if len(waits) == 1:
            raise subprocess.TimeoutExpired("pw-cat", timeout)
        process._exit_code = -9
        return -9

    process.wait = wait
    capture = PipeWireCapture(process_factory=lambda *args, **kwargs: process)
    capture.__enter__()
    capture.close()
    assert process.poll() == -9
    assert len(waits) == 2
