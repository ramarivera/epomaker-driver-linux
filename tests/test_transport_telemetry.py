import errno

import pytest

from epomaker_driver.errors import DeviceUnavailable
from epomaker_driver.transport import Transport


class QueuedIO:
    def __init__(self, queue=()):
        self.queue = list(queue)
        self.reads = 0
        self.read_timeouts = []
        self.writes = []

    def read(self, timeout):
        assert timeout == 0
        self.reads += 1
        self.read_timeouts.append(timeout)
        return self.queue.pop(0) if self.queue else None

    def write(self, data):
        self.writes.append(data)

    def close(self):
        pass


def test_notifications_have_separate_ages_and_unknown_is_not_online():
    now = [10]
    io = QueuedIO([])
    transport = Transport(io, "bluetooth", clock=lambda: now[0])
    assert transport.telemetry() == {
        "battery_raw": None,
        "battery_age_seconds": None,
        "online": None,
        "online_age_seconds": None,
    }
    assert io.writes == [b"\x06\x77" + bytes(64)]
    assert len(io.writes[0]) == 66
    io.queue.extend([b"\x01keypress", b"\x06\x77\x42", b"\x06\x55stale reply"])
    assert transport.telemetry()["battery_raw"] == 66
    now[0] = 14
    io.queue.append(b"\x06\x88")
    value = transport.telemetry()
    assert value == {
        "battery_raw": 66,
        "battery_age_seconds": 4,
        "online": False,
        "online_age_seconds": 0,
    }
    now[0] = 16
    assert transport.telemetry()["online_age_seconds"] == 2
    assert not io.queue


def test_telemetry_query_rate_limit_and_usb_no_write():
    now = [10.0]
    io = QueuedIO()
    transport = Transport(io, "bluetooth", clock=lambda: now[0])
    transport.telemetry()
    transport.telemetry()
    assert len(io.writes) == 1
    now[0] += 4.999
    transport.telemetry()
    assert len(io.writes) == 1
    now[0] = 15.0
    transport.telemetry()
    assert len(io.writes) == 2

    usb = QueuedIO()
    assert Transport(usb, "usb").telemetry()["online"] is None
    assert usb.writes == [] and usb.reads == 0


def test_missing_response_stays_unknown_on_later_poll():
    now = [0.0]
    io = QueuedIO()
    transport = Transport(io, "bluetooth", clock=lambda: now[0])
    assert transport.telemetry()["online"] is None
    now[0] = 5.0
    value = transport.telemetry()
    assert value["battery_raw"] is None
    assert value["battery_age_seconds"] is None
    assert value["online"] is None
    assert value["online_age_seconds"] is None
    assert len(io.writes) == 2


def test_input_budget_is_bounded_and_unrelated_reports_are_not_saved():
    io = QueuedIO([b"\x01keypress"] * 40 + [b"\x06\x77\xff"])
    transport = Transport(io, "bluetooth")
    assert transport.telemetry()["battery_raw"] is None
    assert io.reads == 32 and len(io.queue) == 9
    assert transport.telemetry()["battery_raw"] == 255  # Unknown semantics are preserved.
    assert not any(isinstance(value, bytes) for value in vars(transport).values())


def test_usb_does_not_read_input_and_closed_or_removed_device_fails():
    io = QueuedIO([])
    transport = Transport(io, "usb")
    assert transport.telemetry()["online"] is None
    assert io.reads == 0
    transport.close()
    with pytest.raises(DeviceUnavailable):
        transport.telemetry()
    transport = Transport(io, "bluetooth")
    io.write = lambda _: (_ for _ in ()).throw(OSError(errno.ENODEV, "gone"))
    with pytest.raises(DeviceUnavailable):
        transport.telemetry()
    transport = Transport(QueuedIO(), "bluetooth")
    transport.io.read = lambda _: (_ for _ in ()).throw(OSError(errno.ENODEV, "gone"))
    with pytest.raises(DeviceUnavailable):
        transport.telemetry()


def test_short_notification_has_no_invented_value():
    transport = Transport(QueuedIO([b"\x06\x77", b"\x06", b""]), "bluetooth")
    assert transport.telemetry()["battery_raw"] is None


def test_notifications_wait_until_configuration_transaction_finishes():
    import threading

    io = QueuedIO([b"\x06\x77\x32"])
    transport = Transport(io, "bluetooth")
    started, finished = threading.Event(), threading.Event()
    result = []

    def poll():
        started.set()
        result.append(transport.telemetry())
        finished.set()

    def transfer():
        worker = threading.Thread(target=poll)
        worker.start()
        assert started.wait(1)
        assert not finished.wait(0.02)
        assert io.reads == 0 and io.writes == []
        return worker

    worker = transport.transaction(transfer)
    worker.join(1)
    assert not worker.is_alive()
    assert result[0]["battery_raw"] == 50
