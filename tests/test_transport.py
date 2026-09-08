import errno
import os
import select

import pytest

from epomaker_driver import codec
from epomaker_driver.discovery import DeviceInfo
from epomaker_driver.errors import (
    DevicePermissionError,
    DeviceUnavailable,
    ProtocolError,
    ResponseTimeout,
)
from epomaker_driver.transport import HidrawIO, Transport, feature_ioctl


class IO:
    def __init__(self, responses=()):
        self.pending = list(responses)
        self.queue = []
        self.sent = []
        self.closed = False
        self.feature = bytes([0x8F]) + bytes(63)

    def read(self, _):
        return self.queue.pop(0) if self.queue else None

    def write(self, data):
        self.sent.append(data)
        self.queue.extend(self.pending)

    def set_feature(self, data):
        self.sent.append(data)

    def get_feature(self, *_):
        return self.feature

    def close(self):
        self.closed = True


def make(io, kind="bluetooth"):
    return Transport(io, kind, sleep=lambda _: None)


def test_bluetooth_routing_and_interleaved_input():
    response = bytes([0x8F]) + bytes(63)
    io = IO(
        [
            b"\x01secret keypress",
            b"\x06\x77\x42",
            b"\x06\x88",
            b"\x06\x55" + bytes(64),
            b"\x06\x55" + response,
        ]
    )
    io.queue = [b"\x06\x55" + bytes(64)]  # old reply must be drained
    transport = make(io)
    assert transport.exchange(codec.identify_request(), expected=0x8F) == response
    assert io.sent == [codec.bluetooth_report(codec.identify_request())]
    assert transport.battery == 66
    assert not transport.online


def test_bluetooth_timeout_and_malformed():
    with pytest.raises(ResponseTimeout):
        make(IO()).exchange(codec.identify_request())
    with pytest.raises(ProtocolError, match="64 payload"):
        make(IO([b"\x06\x55bad"])).exchange(codec.identify_request())
    io = IO()
    io.queue = [b"x"] * 128
    with pytest.raises(ProtocolError, match="did not drain"):
        make(io).exchange(codec.identify_request())
    io = IO([b"x"])
    t = make(io)
    counter = iter([0, 0, 2])
    t.clock = lambda: next(counter)
    with pytest.raises(ResponseTimeout):
        t.exchange(codec.identify_request())


def test_usb_reply_and_context():
    io = IO()
    with make(io, "usb") as t:
        assert t.exchange(codec.identify_request(), expected=0x8F) == io.feature
        assert io.sent[0] == codec.usb_report(codec.identify_request())
        io.feature = bytes(64)
        with pytest.raises(ProtocolError):
            t.exchange(codec.identify_request(), expected=0x8F)
        io.feature = bytes(20)
        with pytest.raises(ProtocolError):
            t.exchange(codec.identify_request())
    assert io.closed
    with pytest.raises(DeviceUnavailable):
        t.send(bytes(64))


def test_transport_guards():
    with pytest.raises(ValueError):
        make(IO(), "wrong")
    with pytest.raises(ValueError):
        make(IO()).send(bytes(12))
    with pytest.raises(ValueError):
        make(IO()).exchange(bytes(64), timeout=0)
    info = DeviceInfo("/dev/not-hid", "", 0, 0, 0, b"", None, None)
    with pytest.raises(DeviceUnavailable):
        Transport.open(info)
    for code in (errno.ENODEV, errno.EIO, errno.EBADF, errno.EPERM):

        def fail(code=code):
            raise OSError(code, "failure")

        with pytest.raises(DeviceUnavailable if code != errno.EPERM else OSError):
            make(IO()).transaction(fail)


@pytest.mark.parametrize(
    "report_id,raw,expected",
    [
        (0, bytes([143]) + bytes(63), bytes([143]) + bytes(63)),
        (0, b"\0" + bytes([143]) + bytes(63), bytes([143]) + bytes(63)),
        (6, b"\6" + bytes(64), bytes(64)),
    ],
)
def test_linux_get_feature_normalization(monkeypatch, report_id, raw, expected):
    io = HidrawIO.__new__(HidrawIO)
    io.fd = 123

    def ioctl(fd, code, buffer, mutate):
        assert fd == 123
        assert code == feature_ioctl(7, 65)
        assert buffer[0] == report_id
        buffer[: len(raw)] = raw
        return len(raw)

    monkeypatch.setattr("fcntl.ioctl", ioctl)
    assert io.get_feature(report_id, 64) == expected


@pytest.mark.parametrize("count,first", [(0, 0), (66, 0), (5, 0), (65, 9)])
def test_feature_rejects_truncation(monkeypatch, count, first):
    io = HidrawIO.__new__(HidrawIO)
    io.fd = 123

    def ioctl(fd, code, buffer, mutate):
        buffer[0] = first
        return count

    monkeypatch.setattr("fcntl.ioctl", ioctl)
    with pytest.raises(ProtocolError):
        io.get_feature(6, 64)


def test_open_errors_and_close(monkeypatch):
    def fail_permission(*_):
        raise PermissionError()

    monkeypatch.setattr(os, "open", fail_permission)
    with pytest.raises(DevicePermissionError):
        HidrawIO("/dev/hidraw9")

    def fail_missing(*_):
        raise FileNotFoundError(errno.ENOENT, "missing")

    monkeypatch.setattr(os, "open", fail_missing)
    with pytest.raises(DeviceUnavailable):
        HidrawIO("/dev/hidraw9")
    monkeypatch.setattr(os, "open", lambda *_: 123)
    closed = []
    monkeypatch.setattr(os, "close", closed.append)
    io = HidrawIO("/dev/hidraw9")
    io.close()
    io.close()
    assert closed == [123]
    with pytest.raises(DeviceUnavailable):
        io.write(b"x")


def test_output_io(monkeypatch):
    io = HidrawIO.__new__(HidrawIO)
    io.fd = 123
    monkeypatch.setattr(os, "write", lambda fd, data: len(data))
    io.write(b"abcdef")
    monkeypatch.setattr(os, "write", lambda fd, data: 2)
    with pytest.raises(ProtocolError):
        io.write(b"abcdef")
    seen = []
    monkeypatch.setattr("fcntl.ioctl", lambda *a: seen.append(a))
    io.set_feature(bytes(65))
    assert seen[0][1] == feature_ioctl(6, 65)


@pytest.mark.parametrize(
    "events,raw,error",
    [
        ([], None, None),
        ([(123, select.POLLIN)], b"abc", None),
        ([(123, select.POLLHUP)], None, DeviceUnavailable),
        ([(123, select.POLLIN)], b"", DeviceUnavailable),
        ([(123, select.POLLIN)], "block", None),
    ],
)
def test_poll_read(monkeypatch, events, raw, error):
    class Poll:
        def register(self, *_):
            pass

        def poll(self, *_):
            return events

    monkeypatch.setattr(select, "poll", Poll)

    def read(*_):
        if raw == "block":
            raise BlockingIOError()
        return raw

    monkeypatch.setattr(os, "read", read)
    io = HidrawIO.__new__(HidrawIO)
    io.fd = 123
    if error:
        with pytest.raises(error):
            io.read(0.1)
    else:
        assert io.read(0.1) == (None if raw == "block" else raw)


def test_ioctl_numbers():
    assert feature_ioctl(6, 65) == 0xC0414806
    assert feature_ioctl(7, 65) == 0xC0414807
    for args in [(5, 65), (6, 1), (7, 16384)]:
        with pytest.raises(ValueError):
            feature_ioctl(*args)
