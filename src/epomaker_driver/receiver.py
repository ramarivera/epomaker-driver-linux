"""Shared 2.4 GHz feature-report routing; see docs/receiver.md.

This adapter requires a caller-supplied, verified HID I/O handle. It does not infer
receiver support from VID/PID or open devices through automatic discovery.
"""

import math
import threading
import time
from dataclasses import dataclass

from .errors import DeviceUnavailable, ProtocolError, ResponseTimeout, UnsupportedDevice


@dataclass(frozen=True)
class ReceiverStatus:
    present: bool
    online: bool
    can_send: bool
    can_read: bool
    battery: int | None
    bootloader: bool


def parse_status(raw):
    if len(raw) != 64:
        raise ProtocolError("receiver status must contain 64 payload bytes")
    mode = raw[6]
    if mode not in (0, 1, 2, 3):
        raise ProtocolError("unknown receiver device mask")
    result = {}
    for name, mask, battery, offline in (("keyboard", 1, 1, 3), ("mouse", 2, 2, 4)):
        present = bool(mode & mask)
        result[name] = ReceiverStatus(
            present,
            present and raw[offline] == 0,
            present and raw[5] == 1,
            present and raw[0] == 1,
            raw[battery] if present else None,
            present and raw[8] == 1,
        )
    return result


def positive_time(value, name, *, zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value < 0 or (not zero and value == 0):
        raise ValueError(f"{name} must be {'nonnegative' if zero else 'positive'}")
    return value


class ReceiverBus:
    """Own one handle and one routing lock shared by all its logical endpoints."""

    def __init__(self, io, *, report_id=0, sleep=time.sleep, clock=time.monotonic):
        if type(report_id) is not int or not 0 <= report_id <= 255:
            raise ValueError("feature report ID must be 0..255")
        self.io, self.report_id = io, report_id
        self.sleep, self.clock = sleep, clock
        self.lock = threading.RLock()
        self.closed = False
        self.selected = None
        self.statuses = parse_status(bytes(64))

    def endpoint(self, target):
        if target not in ("keyboard", "mouse"):
            raise ValueError("receiver target must be keyboard or mouse")
        return ReceiverEndpoint(self, target)

    def close(self):
        with self.lock:
            if not self.closed:
                self.io.close()
                self.closed = True
                self.selected = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _check(self):
        if self.closed:
            raise DeviceUnavailable("receiver is closed")

    def _pause(self, seconds, deadline):
        if self.clock() + seconds >= deadline:
            raise ResponseTimeout("receiver readiness deadline exceeded")
        self.sleep(seconds)

    def _send(self, payload):
        self._check()
        # Routing messages bypass the ordinary device checksum encoder.
        self.io.set_feature(bytes([self.report_id]) + bytes(payload).ljust(64, b"\0"))

    def _read(self):
        self._check()
        raw = self.io.get_feature(self.report_id, 64)
        if len(raw) != 64:
            raise ProtocolError("receiver reply must contain 64 payload bytes")
        return raw

    def _status(self, deadline):
        self._pause(0.01, deadline)
        self._send([0xF7])
        self._pause(0.01, deadline)
        self.statuses = parse_status(self._read())
        return self.statuses

    def status(self, *, timeout=1.0):
        positive_time(timeout, "timeout")
        with self.lock:
            return self._status(self.clock() + timeout)

    def _ready(self, target, field, deadline):
        for _ in range(5):
            self._pause(0.1, deadline)
            state = self._status(deadline)[target]
            if state.bootloader:
                raise UnsupportedDevice("receiver reports RF bootloader mode")
            if state.online and getattr(state, field):
                return
        if not state.online:
            raise DeviceUnavailable(f"receiver {target} is absent or offline")
        raise ResponseTimeout(f"receiver {target} did not become {field}")


class ReceiverEndpoint:
    """Transport interface for Keyboard or future mouse drivers on the same bus."""

    kind = "receiver"

    def __init__(self, bus, target):
        self.bus, self.target = bus, target
        self.sleep, self.clock = bus.sleep, bus.clock
        self.closed = False

    @property
    def battery(self):
        return self.bus.statuses[self.target].battery

    @property
    def online(self):
        return self.bus.statuses[self.target].online

    def close(self):
        # Closing a logical keyboard must not disconnect the paired mouse.
        with self.bus.lock:
            self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def transaction(self, operation):
        with self.bus.lock:
            self.bus._check()
            if self.closed:
                raise DeviceUnavailable("receiver endpoint is closed")
            try:
                return operation()
            except Exception:
                # After any failed operation, reselect before the next command.
                self.bus.selected = None
                raise

    def _send(self, command, delay, deadline):
        self.bus._ready(self.target, "can_send", deadline)
        if self.bus.selected != self.target:
            self.bus._pause(0.01, deadline)
            self.bus._send([0xF6, 10 if self.target == "keyboard" else 5])
            self.bus.selected = self.target
        self.bus._pause(0.01 + delay, deadline)
        self.bus._send(command)

    def send(self, command, *, delay=None, timeout=1.0):
        if len(command) != 64:
            raise ValueError("expected a 64-byte device command")
        positive_time(timeout, "timeout")
        delay = positive_time(0.01 if delay is None else delay, "delay", zero=True)
        return self.transaction(lambda: self._send(command, delay, self.clock() + timeout))

    def exchange(self, command, *, expected=None, timeout=2.0, send_delay=None, read_delay=None):
        if len(command) != 64:
            raise ValueError("expected a 64-byte device command")
        positive_time(timeout, "timeout")
        send_delay = positive_time(
            0.01 if send_delay is None else send_delay, "send_delay", zero=True
        )
        read_delay = positive_time(
            0.01 if read_delay is None else read_delay, "read_delay", zero=True
        )

        def operation():
            deadline = self.clock() + timeout
            self._send(command, send_delay, deadline)
            self.bus._pause(read_delay, deadline)
            self.bus._ready(self.target, "can_read", deadline)
            self.bus._pause(0.01, deadline)
            self.bus._send([0xFC])
            self.bus._pause(0.01, deadline)
            result = self.bus._read()
            if expected is not None and result[0] != expected:
                raise ProtocolError("receiver reply has unexpected command")
            return result

        return self.transaction(operation)
