import errno

import pytest

from epomaker_driver.errors import DeviceUnavailable
from epomaker_driver.transport import Transport


class QueuedIO:
    def __init__(self, queue):
        self.queue = list(queue)
        self.reads = 0

    def read(self, timeout):
        assert timeout == 0
        self.reads += 1
        return self.queue.pop(0) if self.queue else None

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
    io.read = lambda _: (_ for _ in ()).throw(OSError(errno.ENODEV, "gone"))
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
        assert io.reads == 0
        return worker

    worker = transport.transaction(transfer)
    worker.join(1)
    assert not worker.is_alive()
    assert result[0]["battery_raw"] == 50
