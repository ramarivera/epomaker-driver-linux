"""Bounded, in-memory PipeWire monitor capture for Glyph audio workflows."""

from __future__ import annotations

import math
import os
import selectors
import struct
import subprocess
import time
from threading import Event


class AudioCaptureError(RuntimeError):
    """A capture process or PCM stream failed."""


class PipeWireCapture:
    """Read native-endian normalized float32 monitor samples from ``pw-cat``."""

    def __init__(
        self,
        *,
        target="auto",
        read_timeout=1.0,
        chunk_samples=480,
        stop_event=None,
        process_factory=subprocess.Popen,
    ):
        if type(target) is not str or not target or "\x00" in target:
            raise ValueError("PipeWire target must be a nonempty string without NUL")
        if isinstance(read_timeout, bool) or not isinstance(read_timeout, (int, float)):
            raise ValueError("read timeout must be a finite positive number")
        if not math.isfinite(read_timeout) or read_timeout <= 0:
            raise ValueError("read timeout must be a finite positive number")
        if type(chunk_samples) is not int or not 1 <= chunk_samples <= 65536:
            raise ValueError("chunk_samples must be an integer in 1..65536")
        self.target = target
        self.read_timeout = float(read_timeout)
        self.chunk_samples = chunk_samples
        self.stop_event = stop_event or Event()
        self.process_factory = process_factory
        self.process = None
        self._buffer = bytearray()
        self._selector = None

    @property
    def argv(self):
        return [
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
            self.target,
            "-",
        ]

    def __enter__(self):
        if self.process is None:
            try:
                self.process = self.process_factory(
                    self.argv,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError as error:
                raise AudioCaptureError(
                    "pw-cat is not installed; install PipeWire tools"
                ) from error
            try:
                self._selector = selectors.DefaultSelector()
                os.set_blocking(self.process.stdout.fileno(), False)
                self._selector.register(self.process.stdout, selectors.EVENT_READ)
            except Exception as error:
                self.close()
                raise AudioCaptureError("could not monitor pw-cat output") from error
        return self

    def read_samples(self, count=None):
        if self.process is None:
            raise AudioCaptureError("capture is not started")
        count = self.chunk_samples if count is None else count
        if type(count) is not int or not 1 <= count <= self.chunk_samples:
            raise ValueError(f"sample count must be an integer in 1..{self.chunk_samples}")
        wanted = count * 4
        deadline = time.monotonic() + self.read_timeout
        while len(self._buffer) < wanted:
            if self.stop_event.is_set():
                raise AudioCaptureError("audio capture stopped")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AudioCaptureError("timed out waiting for PipeWire PCM")
            events = self._selector.select(min(0.1, remaining))
            if not events:
                continue
            try:
                data = os.read(self.process.stdout.fileno(), wanted - len(self._buffer))
            except BlockingIOError:
                continue
            if data:
                self._buffer.extend(data)
                continue
            code = self.process.poll()
            if code is None:
                raise AudioCaptureError("pw-cat closed its output before exiting")
            raise AudioCaptureError(f"pw-cat exited with status {code}")
        raw = bytes(self._buffer[:wanted])
        del self._buffer[:wanted]
        samples = list(struct.unpack(f"={count}f", raw))
        if not all(math.isfinite(sample) for sample in samples):
            raise AudioCaptureError("PipeWire returned non-finite PCM")
        return samples

    def close(self):
        process, self.process = self.process, None
        selector, self._selector = self._selector, None
        self._buffer.clear()
        if selector is not None:
            selector.close()
        if process is None:
            return
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1)
                return
            process.wait(timeout=1)
        finally:
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()

    def __exit__(self, *_):
        self.close()
