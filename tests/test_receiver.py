import threading

import pytest

from epomaker_driver import codec
from epomaker_driver.device import Keyboard
from epomaker_driver.errors import (
    DeviceUnavailable,
    ProtocolError,
    ResponseTimeout,
    UnsupportedDevice,
)
from epomaker_driver.receiver import ReceiverBus, parse_status


class Wire:
    def __init__(self, firmware):
        self.firmware = firmware
        self.sent = []
        self.status = bytearray([1, 80, 60, 0, 0, 1, 3, 0, 0]) + bytearray(55)
        self.pending = None
        self.mode = None
        self.closed = False
        self.selected = None
        self.report_id = 0
        self.status_count = 0
        self.reply_override = None

    def set_feature(self, report):
        assert len(report) == 65 and report[0] == self.report_id
        self.sent.append(report)
        payload = report[1:]
        if payload[0] == 0xF7:
            self.mode = "status"
            self.status_count += 1
        elif payload[0] == 0xF6:
            self.selected = payload[1]
        elif payload[0] == 0xFC:
            assert self.pending is not None
            self.mode = "reply"
        else:
            assert self.selected in (5, 10)
            if payload[0] >= 0x80:
                self.pending = self.firmware.exchange(payload)
            else:
                self.firmware.send(payload)

    def get_feature(self, report_id, length):
        assert (report_id, length) == (self.report_id, 64)
        if self.reply_override is not None:
            return self.reply_override
        if self.mode == "status":
            return bytes(self.status)
        assert self.mode == "reply"
        return self.pending

    def close(self):
        self.closed = True


@pytest.fixture
def receiver(firmware):
    wire = Wire(firmware)
    elapsed = [0.0]

    def sleep(seconds):
        elapsed[0] += seconds

    bus = ReceiverBus(wire, sleep=sleep, clock=lambda: elapsed[0])
    return bus, wire


def test_glyph_round_trip_through_receiver(receiver, firmware):
    bus, wire = receiver
    endpoint = bus.endpoint("keyboard")
    keyboard = Keyboard(endpoint)
    assert keyboard.identify()["device_id"] == 3059
    assert [p[1] for p in wire.sent] == [0xF7, 0xF6, 0x8F, 0xF7, 0xFC]
    assert wire.sent[1] == bytes([0, 0xF6, 10]) + bytes(62)
    assert wire.sent[0] == bytes([0, 0xF7]) + bytes(63)
    assert wire.sent[-1] == bytes([0, 0xFC]) + bytes(63)
    keyboard.set_key(9, bytes([0, 0, 5, 0]))
    assert keyboard.read_matrix()[36:40] == bytes([0, 0, 5, 0])
    assert endpoint.online and endpoint.battery == 80
    mouse = bus.endpoint("mouse")
    mouse.exchange(codec.identify_request(), expected=0x8F)
    endpoint.exchange(codec.identify_request(), expected=0x8F)
    assert [p[2] for p in wire.sent if p[1] == 0xF6] == [10, 5, 10]
    assert mouse.battery == 60


@pytest.mark.parametrize("mask", range(4))
def test_device_status_mask(mask):
    raw = bytes([1, 90, 55, 0, 1, 1, mask, 0, 1]) + bytes(55)
    state = parse_status(raw)
    assert state["keyboard"].present == bool(mask & 1)
    assert state["mouse"].present == bool(mask & 2)
    assert state["keyboard"].online == bool(mask & 1)
    assert not state["mouse"].online
    assert state["mouse"].bootloader == bool(mask & 2)
    assert state["keyboard"].battery == (90 if mask & 1 else None)
    with pytest.raises(ProtocolError):
        parse_status(raw[:9])
    with pytest.raises(ProtocolError):
        parse_status(raw[:6] + bytes([4]) + raw[7:])


@pytest.mark.parametrize(
    "field,error", [(3, DeviceUnavailable), (5, ResponseTimeout), (8, UnsupportedDevice)]
)
def test_unavailable_receiver_never_sends_device_command(receiver, field, error):
    bus, wire = receiver
    wire.status[field] = 1 if field in (3, 8) else 0
    with pytest.raises(error):
        bus.endpoint("keyboard").send(codec.packet([7]))
    assert all(p[1] == 0xF7 for p in wire.sent)
    assert wire.status_count == (1 if field == 8 else 5)
    assert bus.selected is None


def test_read_timeout_does_not_resend_mutating_command(receiver):
    bus, wire = receiver
    wire.status[0] = 0
    with pytest.raises(ResponseTimeout, match="can_read"):
        bus.endpoint("keyboard").exchange(codec.identify_request())
    assert sum(p[1] == 0x8F for p in wire.sent) == 1
    assert not any(p[1] == 0xFC for p in wire.sent)
    assert bus.selected is None


def test_ready_after_retry_and_deadline(receiver):
    bus, wire = receiver
    get = wire.get_feature

    def delayed(*args):
        wire.status[5] = int(wire.status_count >= 3)
        return get(*args)

    wire.get_feature = delayed
    bus.endpoint("keyboard").send(codec.packet([7]), delay=0)
    assert wire.status_count == 3
    wire.sent.clear()
    with pytest.raises(ResponseTimeout, match="deadline"):
        bus.endpoint("keyboard").exchange(codec.identify_request(), timeout=0.05)
    assert not wire.sent


def test_reply_validation_and_selection_invalidation(receiver):
    bus, wire = receiver
    endpoint = bus.endpoint("keyboard")
    with pytest.raises(ProtocolError, match="unexpected command"):
        endpoint.exchange(codec.identify_request(), expected=0x83)
    assert bus.selected is None
    wire.reply_override = b"bad"
    with pytest.raises(ProtocolError, match="64 payload"):
        bus.status()
    assert bus.statuses["keyboard"].battery == 80


def test_handle_lifetime_and_report_id(receiver):
    bus, wire = receiver
    wire.report_id = bus.report_id = 7
    keyboard = bus.endpoint("keyboard")
    with keyboard:
        assert bus.status()["mouse"].battery == 60
    with pytest.raises(DeviceUnavailable, match="endpoint is closed"):
        keyboard.send(codec.packet([7]))
    assert not wire.closed
    with bus:
        bus.endpoint("mouse").send(codec.packet([7]))
    assert wire.closed
    bus.close()
    with pytest.raises(DeviceUnavailable, match="receiver is closed"):
        bus.status()


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True, "1"])
def test_invalid_timeouts(receiver, value):
    bus, wire = receiver
    endpoint = bus.endpoint("keyboard")
    for call in [
        lambda: bus.status(timeout=value),
        lambda: endpoint.send(bytes(64), timeout=value),
        lambda: endpoint.exchange(bytes(64), timeout=value),
    ]:
        with pytest.raises(ValueError):
            call()
    assert not wire.sent


def test_invalid_inputs(receiver):
    bus, wire = receiver
    endpoint = bus.endpoint("keyboard")
    with pytest.raises(ValueError):
        ReceiverBus(wire, report_id=256)
    with pytest.raises(ValueError):
        bus.endpoint("all")
    with pytest.raises(ValueError):
        endpoint.send(b"short")
    with pytest.raises(ValueError):
        endpoint.exchange(b"short")
    with pytest.raises(ValueError):
        endpoint.send(bytes(64), delay=-1)
    with pytest.raises(ValueError):
        endpoint.exchange(bytes(64), read_delay=float("nan"))
    assert not wire.sent


def test_multi_page_transactions_cannot_switch_target_midway(receiver):
    bus, wire = receiver
    keyboard, mouse = bus.endpoint("keyboard"), bus.endpoint("mouse")
    entered, attempted, completed = threading.Event(), threading.Event(), threading.Event()

    def competing():
        entered.wait(2)
        attempted.set()
        mouse.send(codec.packet([7]))
        completed.set()

    worker = threading.Thread(target=competing)
    worker.start()

    def operation():
        keyboard.send(codec.packet([7]))
        entered.set()
        assert attempted.wait(2)
        assert not completed.is_set()
        keyboard.send(codec.packet([8]))

    keyboard.transaction(operation)
    worker.join(2)
    assert completed.is_set()
    opcodes = [p[1] for p in wire.sent if p[1] != 0xF7]
    assert opcodes == [0xF6, 7, 8, 0xF6, 7]
