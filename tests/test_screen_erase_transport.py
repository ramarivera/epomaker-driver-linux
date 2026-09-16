import threading

import pytest

from epomaker_driver.errors import ProtocolError, ResponseTimeout, UnsupportedDevice
from epomaker_driver.transport import Transport


class IO:
    def __init__(self, queue=()):
        self.queue = list(queue)
        self.reads = []
        self.writes = []

    def read(self, timeout):
        self.reads.append(timeout)
        return self.queue.pop(0) if self.queue else None

    def write(self, data):
        self.writes.append(data)

    def close(self):
        pass


class Clock:
    def __init__(self):
        self.value = 0

    def __call__(self):
        self.value += 0.25
        return self.value


def test_usb_completion_drains_stale_and_waits_for_new_report():
    event = b"\x2c\x00\x00" + bytes(61)
    io = IO([event, bytes(64)])
    transport = Transport(io, "usb", sleep=lambda _: None, vendor_reports={0: 64})
    token = transport.prepare_screen_erase_wait()
    assert token == 1
    io.queue.extend([b"\x00" + event, event])
    assert transport.wait_screen_erase(token, timeout=1)
    assert transport._screen_erase_completions == 2
    assert io.writes == []


def test_bluetooth_completion_is_counted_by_decode_before_command_ack():
    event = b"\x06\x66\x2c\x00\x00" + bytes(61)
    io = IO()
    transport = Transport(io, "bluetooth", sleep=lambda _: None, vendor_reports={6: 65})
    token = transport.prepare_screen_erase_wait()
    assert token == 0
    # A completion consumed by exchange's decoder before the ACK must survive.
    assert transport._decode(event) is None
    assert transport.wait_screen_erase(token, timeout=1)
    assert io.reads == [0]


def test_completion_rejects_wrong_prefix_or_length():
    valid = b"\x2c\x00\x00" + bytes(61)
    io = IO([b"\x2c\x00\x01" + bytes(61), valid[:-1]])
    transport = Transport(io, "usb", sleep=lambda _: None, clock=Clock(), vendor_reports={0: 64})
    assert transport.prepare_screen_erase_wait() == 0
    with pytest.raises(ResponseTimeout):
        transport.wait_screen_erase(0, timeout=1)


def test_cancel_and_validation():
    transport = Transport(IO(), "usb", sleep=lambda _: None, vendor_reports={0: 64})
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ProtocolError, match="uncertain"):
        transport.wait_screen_erase(0, cancel=cancel)
    with pytest.raises(ValueError):
        transport.wait_screen_erase(True)
    with pytest.raises(ValueError):
        transport.wait_screen_erase(1)
    with pytest.raises(UnsupportedDevice):
        Transport(IO(), "usb").prepare_screen_erase_wait()


def test_usb_nonzero_id_and_unframed_zero_are_scoped():
    event = b"\x2c\x00\x00" + bytes(61)
    io = IO([event, b"\x00" + event[:-1], b"\x09" + event])
    transport = Transport(io, "usb", sleep=lambda _: None, vendor_reports={7: 64, 8: 64})
    # A report-0 style unnumbered event is not valid when only nonzero IDs exist.
    assert transport.prepare_screen_erase_wait() == 0
    io.queue.append(b"\x07" + event)
    assert transport.wait_screen_erase(0, timeout=1)


def test_queue_with_more_than_128_reports_is_rejected():
    io = IO([bytes(64)] * 129)
    transport = Transport(io, "usb", vendor_reports={0: 64})
    with pytest.raises(ProtocolError, match="did not drain"):
        transport.prepare_screen_erase_wait()


@pytest.mark.parametrize("raw", [b"\x00\x2c\x00\x00" + bytes(61), b"\x01\x2c\x00\x00" + bytes(61)])
def test_unnumbered_usb_rejects_synthetic_id_and_normal_keyboard_report(raw):
    io = IO([raw])
    transport = Transport(io, "usb", clock=Clock(), vendor_reports={0: 64})
    assert transport.prepare_screen_erase_wait() == 0
    with pytest.raises(ResponseTimeout):
        transport.wait_screen_erase(0, timeout=1)


@pytest.mark.parametrize(
    "raw",
    [
        b"\x06\x55\x2c\x00\x00" + bytes(61),
        b"\x01\x66\x2c\x00\x00" + bytes(61),
        b"\x06\x66\x2c\x00\x00",
    ],
)
def test_bluetooth_requires_vendor_marker_id_and_descriptor_length(raw):
    transport = Transport(IO([raw]), "bluetooth", clock=Clock(), vendor_reports={6: 65})
    assert transport.prepare_screen_erase_wait() == 0
    with pytest.raises(ResponseTimeout):
        transport.wait_screen_erase(0, timeout=1)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timeout": 0},
        {"timeout": float("inf")},
        {"timeout": True},
        {"token": -1},
        {"cancel": 42},
        {"progress": 42},
    ],
)
def test_invalid_wait_arguments_never_read(kwargs):
    io = IO()
    transport = Transport(io, "usb", vendor_reports={0: 64})
    with pytest.raises(ValueError):
        transport.wait_screen_erase(**({"token": 0} | kwargs))
    assert not io.reads


def test_missing_mapping_and_closed_transport_cannot_wait():
    from epomaker_driver.errors import DeviceUnavailable

    io = IO()
    transport = Transport(io, "usb")
    with pytest.raises(UnsupportedDevice):
        transport.wait_screen_erase(0)
    transport.close()
    for call in (transport.prepare_screen_erase_wait, lambda: transport.wait_screen_erase(0)):
        with pytest.raises(DeviceUnavailable):
            call()
    assert not io.reads


def test_real_bluetooth_exchange_preserves_completion_before_ack():
    from epomaker_driver import codec

    event = bytes.fromhex("06662c0000") + bytes(61)
    ack = bytes.fromhex("0655acaaaa5555") + bytes(59)

    class ReplyIO(IO):
        def write(self, data):
            super().write(data)
            self.queue.extend([event, ack])

    io = ReplyIO()
    transport = Transport(
        io, "bluetooth", sleep=lambda _: None, clock=Clock(), vendor_reports={6: 65}
    )
    token = transport.prepare_screen_erase_wait()
    assert transport.exchange(codec.packet([0xAC]), expected=0xAC, timeout=10) == ack[2:]
    reads = len(io.reads)
    assert transport.wait_screen_erase(token)
    assert len(io.reads) == reads and len(io.writes) == 1


def test_open_closes_handle_when_descriptor_parsing_fails(monkeypatch):
    from epomaker_driver import transport as module
    from epomaker_driver.discovery import DeviceInfo

    class OpenIO(IO):
        closed = False

        def verify(self, device):
            pass

        def close(self):
            self.closed = True

    io = OpenIO()
    monkeypatch.setattr(module, "HidrawIO", lambda _: io)
    device = DeviceInfo("/dev/test", "", 3, 0x3151, 0x5002, b"\xfe", "usb", 0)
    with pytest.raises(ProtocolError):
        Transport.open(device)
    assert io.closed
