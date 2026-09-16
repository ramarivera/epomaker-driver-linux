import threading

import pytest

from epomaker_driver import codec
from epomaker_driver.device import Keyboard
from epomaker_driver.errors import ProtocolError, ResponseTimeout, UnsupportedDevice
from epomaker_driver.transport import Transport


class EraseIO:
    def __init__(self, *, model=3059, boot=False, completion=True):
        self.now = 0
        self.sent = []
        self.queue = []
        self.feature = bytearray(64)
        self.feature[0] = 0x8F
        self.feature[1:5] = model.to_bytes(4, "little")
        self.feature[9] = boot
        self.completion = completion

    def set_feature(self, data):
        self.sent.append(data)
        if data[1] == 0xAC:
            self.feature = bytearray(bytes.fromhex("acaaaa5555") + bytes(59))
            if self.completion:
                self.queue.append(bytes.fromhex("2c0000") + bytes(61))

    def get_feature(self, report_id, size):
        return bytes(self.feature)

    def read(self, _timeout):
        self.now += _timeout
        return self.queue.pop(0) if self.queue else None

    def write(self, data):
        self.sent.append(data)

    def close(self):
        pass


def keyboard(io, kind="usb"):
    return Keyboard(
        Transport(io, kind, sleep=lambda _: None, clock=lambda: io.now, vendor_reports={0: 64})
    )


def test_erase_ack_and_completion_are_one_transaction():
    io = EraseIO()
    result = keyboard(io).erase_screen(timeout=1)
    assert result == {"acknowledged": True, "completion_received": True, "pixels_verified": False}
    assert [packet[1] for packet in io.sent].count(0xAC) == 1


def test_no_qualifying_completion_report_rejects_before_ac():
    io = EraseIO()
    kb = Keyboard(Transport(io, "usb", sleep=lambda _: None, vendor_reports={}))
    with pytest.raises(UnsupportedDevice, match="completion report"):
        kb.erase_screen(timeout=1)
    assert not any(packet[1] == 0xAC for packet in io.sent)


def test_timeout_after_ack_does_not_retry():
    io = EraseIO(completion=False)
    kb = keyboard(io)
    with pytest.raises(ResponseTimeout):
        kb.erase_screen(timeout=0.01)
    assert [packet[1] for packet in io.sent].count(0xAC) == 1


def test_cancel_before_and_after_ack():
    io = EraseIO()
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ProtocolError, match="cancelled"):
        keyboard(io).erase_screen(cancel=cancel)
    assert not io.sent

    io = EraseIO(completion=False)
    cancel = threading.Event()

    def cancel_after_ack(_elapsed):
        cancel.set()

    with pytest.raises(ProtocolError, match="cancelled"):
        keyboard(io).erase_screen(timeout=1, cancel=cancel, progress=cancel_after_ack)
    assert [packet[1] for packet in io.sent].count(0xAC) == 1


@pytest.mark.parametrize("model,boot", [(2895, False), (3059, True)])
def test_wrong_model_or_boot_sends_no_erase(model, boot):
    io = EraseIO(model=model, boot=boot)
    with pytest.raises(UnsupportedDevice):
        keyboard(io).erase_screen(timeout=1)
    assert not any(packet[1] == 0xAC for packet in io.sent)


@pytest.mark.parametrize(
    "timeout",
    [True, False, 0, -1, 301, float("inf"), float("nan"), "90", 10**1000],
    ids=["true", "false", "zero", "negative", "large", "inf", "nan", "text", "huge"],
)
def test_invalid_timeout_never_sends_even_identity(timeout):
    io = EraseIO()
    with pytest.raises(ValueError):
        keyboard(io).erase_screen(timeout=timeout)
    assert io.sent == []


@pytest.mark.parametrize("kwargs", [{"cancel": object()}, {"progress": 42}])
def test_invalid_callbacks_reject_before_device_access(kwargs):
    io = EraseIO()
    with pytest.raises(ValueError):
        keyboard(io).erase_screen(**kwargs)
    assert not io.sent


def test_transport_ownership_extends_through_completion_wait():
    io = EraseIO(completion=False)
    waiting = threading.Event()
    release = threading.Event()
    attempted = threading.Event()
    sent = threading.Event()
    original_read = io.read

    def read(timeout):
        if timeout:
            waiting.set()
            if not release.wait(2):
                raise AssertionError("test did not release completion")
            return bytes.fromhex("2c0000") + bytes(61)
        return original_read(timeout)

    io.read = read
    kb = keyboard(io)
    results = []

    def erase():
        try:
            results.append(kb.erase_screen())
        except Exception as error:
            results.append(error)

    def write():
        attempted.set()
        kb.transport.send(codec.packet([7]))
        sent.set()

    eraser = threading.Thread(target=erase)
    writer = threading.Thread(target=write)
    eraser.start()
    try:
        assert waiting.wait(1)
        writer.start()
        assert attempted.wait(1)
        assert not sent.wait(0.05)
        assert [packet[1] for packet in io.sent] == [0x8F, 0xAC]
    finally:
        release.set()
        eraser.join(2)
        if writer.ident is not None:
            writer.join(2)
    assert not eraser.is_alive() and not writer.is_alive()
    assert results == [
        {"acknowledged": True, "completion_received": True, "pixels_verified": False}
    ]
    assert sent.is_set() and io.sent[-1][1] == 7
