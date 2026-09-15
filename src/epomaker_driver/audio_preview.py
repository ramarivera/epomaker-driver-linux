"""Short-lived audio analysis for the app; no keyboard writes or PCM retention."""

from __future__ import annotations

import math
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from .audio_capture import AudioCaptureError, PipeWireCapture
from .audio_spectrum import SpectrumAnalyzer


class AudioPreview:
    """Own one capture worker and its expiring browser polling lease."""

    def __init__(
        self,
        capture_factory: Callable[..., Any] = PipeWireCapture,
        *,
        clock: Callable[[], float] = time.monotonic,
        lease: float = 5.0,
    ) -> None:
        if isinstance(lease, bool) or not isinstance(lease, (int, float)):
            raise ValueError("lease must be a finite positive number")
        if not math.isfinite(float(lease)) or lease <= 0:
            raise ValueError("lease must be a finite positive number")
        if not callable(clock):
            raise ValueError("clock must be callable")
        self.capture_factory, self.clock, self.lease = capture_factory, clock, float(lease)
        self.lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.deadline = 0.0
        self.state: dict[str, Any] = {
            "running": False,
            "session": None,
            "sequence": 0,
            "bands": None,
            "error": None,
        }

    def status(self) -> dict[str, Any]:
        with self.lock:
            result = dict(self.state)
            result["bands"] = None if self.state["bands"] is None else list(self.state["bands"])
            return result

    def start(self, target: str = "auto", **settings: Any) -> dict[str, str]:
        with self.lock:
            if self.state["running"]:
                raise ValueError("audio preview is already running; stop it before starting again")
        # Validate analysis settings before capture __enter__ can spawn pw-cat.
        analyzer = SpectrumAnalyzer(**settings)
        event = threading.Event()
        capture = self.capture_factory(target=target, chunk_samples=512, stop_event=event)
        self.stop()
        token = uuid.uuid4().hex
        with self.lock:
            self.stop_event = event
            self.deadline = self.clock() + self.lease
            self.state = {
                "running": True,
                "session": token,
                "sequence": 0,
                "bands": None,
                "error": None,
            }
            worker = threading.Thread(
                target=self._run, args=(token, capture, analyzer, event), daemon=True
            )
            self.thread = worker
        try:
            worker.start()
        except BaseException:
            cleanup_error = None
            event.set()
            try:
                capture.close()
            except Exception as error:
                cleanup_error = str(error)
            finally:
                with self.lock:
                    self.state["running"] = False
                    self.state["error"] = cleanup_error
                    self.thread = None
            raise
        return {"session": token}

    def sample(self, session: str) -> dict[str, Any]:
        with self.lock:
            if session != self.state["session"]:
                raise ValueError("audio preview session ended; start again")
            if not self.state["running"]:
                result = dict(self.state)
                result["bands"] = None if self.state["bands"] is None else list(self.state["bands"])
                return result
            self.deadline = self.clock() + self.lease
        return self.status()

    def stop(self, session: str | None = None) -> dict[str, Any]:
        with self.lock:
            current = self.state["session"]
            if session is not None and session != current:
                return {"ok": True, "error": None}
            event, worker, token = self.stop_event, self.thread, current
            event.set()
        if worker is not None and worker is not threading.current_thread():
            worker.join()
        with self.lock:
            error = self.state["error"] if token == self.state["session"] else None
            if worker is self.thread:
                self.thread = None
            if token == self.state["session"]:
                self.state["running"] = False
        return {"ok": error is None, "error": error}

    def _record_error(self, token: str, error: BaseException) -> None:
        with self.lock:
            if token == self.state["session"]:
                self.state["error"] = str(error)

    def _run(
        self, token: str, capture: Any, analyzer: SpectrumAnalyzer, event: threading.Event
    ) -> None:
        try:
            with capture:
                while not event.is_set():
                    with self.lock:
                        expired = token == self.state["session"] and self.clock() >= self.deadline
                    if expired:
                        raise RuntimeError(
                            "audio preview stopped because the browser stopped polling"
                        )
                    try:
                        samples = capture.read_samples()
                    except AudioCaptureError as error:
                        # PipeWireCapture reports event cancellation this way;
                        # close errors from __exit__ still escape the context.
                        if event.is_set() and str(error) == "audio capture stopped":
                            break
                        raise
                    if event.is_set():
                        break
                    bands = analyzer.process(samples)
                    with self.lock:
                        if token != self.state["session"] or not self.state["running"]:
                            break
                        self.state["sequence"] += 1
                        self.state["bands"] = list(bands)
        except Exception as error:
            self._record_error(token, error)
        finally:
            with self.lock:
                if token == self.state["session"]:
                    self.state["running"] = False
