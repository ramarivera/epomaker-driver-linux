"""Linux hidraw I/O and serialized protocol exchanges. No input-event logging.

Report normalization follows the kernel raw-report API, not the Windows shim.
See docs/provenance.md for sources and tests/test_transport.py for fixtures.
"""

from __future__ import annotations

import errno
import fcntl
import os
import select
import threading
import time
from collections.abc import Callable

from .discovery import DeviceInfo
from .errors import DevicePermissionError, DeviceUnavailable, ProtocolError, ResponseTimeout


def feature_ioctl(number: int, length: int) -> int:
    if number not in (6, 7) or not 2 <= length < 16384:
        raise ValueError("invalid feature ioctl")
    return (3 << 30) | (length << 16) | (ord("H") << 8) | number


class HidrawIO:
    """Own a single nonblocking HID descriptor; injectable for deterministic tests."""

    def __init__(self, path: str):
        self.fd = -1
        try:
            self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
        except PermissionError as error:
            raise DevicePermissionError(
                f"No access to {path}; configure device permissions (see docs/hardware.md)"
            ) from error
        except OSError as error:
            raise DeviceUnavailable(f"Cannot open {path}: {error.strerror}") from error

    def close(self):
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def _check(self):
        if self.fd < 0:
            raise DeviceUnavailable("device handle is closed")

    def write(self, data: bytes):
        self._check()
        if os.write(self.fd, data) != len(data):
            raise ProtocolError("short HID output write")

    def set_feature(self, data: bytes):
        self._check()
        result = fcntl.ioctl(self.fd, feature_ioctl(6, len(data)), data)
        # For immutable buffers Python returns a byte buffer; errno still propagates.
        return result

    def get_feature(self, report_id: int, size: int) -> bytes:
        self._check()
        buffer = bytearray([report_id]) + bytearray(size)
        count = fcntl.ioctl(self.fd, feature_ioctl(7, len(buffer)), buffer, True)
        if not 0 < count <= len(buffer):
            raise ProtocolError("invalid feature response length")
        data = bytes(buffer[:count])
        # Linux can return unnumbered USB reports without a synthetic zero byte.
        if report_id == 0 and count == size:
            return data
        if count == size + 1 and data[0] == report_id:
            return data[1:]
        raise ProtocolError(f"feature report has unexpected framing/length: {count}")

    def read(self, timeout: float) -> bytes | None:
        self._check()
        poller = select.poll()
        poller.register(self.fd, select.POLLIN | select.POLLERR | select.POLLHUP)
        events = poller.poll(max(0, int(timeout * 1000)))
        if not events:
            return None
        if events[0][1] & (select.POLLERR | select.POLLHUP | select.POLLNVAL):
            raise DeviceUnavailable("HID device disconnected")
        try:
            data = os.read(self.fd, 8192)
        except BlockingIOError:
            return None
        if not data:
            raise DeviceUnavailable("HID device returned EOF")
        return data


class Transport:
    def __init__(self, io, kind: str, *, sleep=time.sleep, clock=time.monotonic):
        if kind not in ("usb", "bluetooth"):
            raise ValueError("unsupported transport")
        self.io = io
        self.kind = kind
        self._lock = threading.RLock()
        self.sleep = sleep
        self.clock = clock
        self.battery: int | None = None
        self.online = True
        self.closed = False

    @classmethod
    def open(cls, device: DeviceInfo):
        if device.command_transport not in ("usb", "bluetooth"):
            raise DeviceUnavailable("not a supported command collection")
        return cls(HidrawIO(device.path), device.command_transport)

    def close(self):
        with self._lock:
            self.io.close()
            self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _check(self, command: bytes):
        if self.closed:
            raise DeviceUnavailable("transport is closed")
        if len(command) != 64:
            raise ValueError("expected a 64-byte command payload")

    def _send(self, command: bytes, delay: float):
        self._check(command)
        self.sleep(delay)
        if self.kind == "usb":
            self.io.set_feature(b"\0" + command)
        else:
            self.io.write(b"\x06\x55" + command)

    def send(self, command: bytes, *, delay: float | None = None):
        with self._lock:
            self._send(
                command, delay if delay is not None else (0.1 if self.kind == "bluetooth" else 0.01)
            )

    def _decode(self, raw: bytes) -> bytes | None:
        # This node also carries normal keypress reports; discard them, never persist them.
        if len(raw) < 2 or raw[0] != 6:
            return None
        if raw[1] == 0x77 and len(raw) >= 3:
            self.battery, self.online = raw[2], True
        elif raw[1] == 0x88:
            self.online = False
        elif raw[1] == 0x55:
            if len(raw) != 66:
                raise ProtocolError("Bluetooth command reply must contain 64 payload bytes")
            return raw[2:]
        return None

    def exchange(
        self,
        command: bytes,
        *,
        expected: int | None = None,
        timeout: float = 1.0,
        send_delay: float | None = None,
        read_delay: float | None = None,
    ) -> bytes:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        with self._lock:
            self._check(command)
            if self.kind == "bluetooth":
                # Discard old replies before sending; bounded even while the user types.
                for _ in range(128):
                    old = self.io.read(0)
                    if old is None:
                        break
                    self._decode(old)
                else:
                    raise ProtocolError("input queue did not drain")
            self.send(command, delay=send_delay)
            if self.kind == "usb":
                self.sleep(0.01 if read_delay is None else read_delay)
                data = self.io.get_feature(0, 64)
                if len(data) != 64 or (expected is not None and data[0] != expected):
                    raise ProtocolError("USB reply has unexpected length or command")
                return data
            deadline = self.clock() + timeout
            while (remaining := deadline - self.clock()) > 0:
                raw = self.io.read(remaining)
                if raw is None:
                    break
                data = self._decode(raw)
                if data is not None and (expected is None or data[0] == expected):
                    return data
            raise ResponseTimeout(f"no reply to command 0x{command[0]:02x}")

    def transaction(self, operation: Callable):
        """Keep a multi-page operation atomic relative to other local requests."""
        with self._lock:
            try:
                return operation()
            except OSError as error:
                if error.errno in (errno.ENODEV, errno.EIO, errno.EBADF):
                    raise DeviceUnavailable("device disconnected during transaction") from error
                raise
