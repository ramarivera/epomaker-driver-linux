import pytest

from epomaker_driver.errors import ProtocolError, UnsupportedDevice
from epomaker_driver.he_calibration import HECalibrationMixin, validate_duration


class FakeTransport:
    kind = "usb"

    def __init__(self):
        self.now = 0.0
        self.sent = []
        self.pages = [bytes([i, i + 1]) * 32 for i in range(0, 8, 2)]
        self.fail_send = set()

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds

    def send(self, command):
        self.sent.append(command)
        if len(self.sent) in self.fail_send:
            raise OSError("send failure")

    def exchange(self, command, *, expected=None, send_delay=None, read_delay=None):
        assert expected is None
        assert send_delay == read_delay == 0.001
        if command[0] != 0xE5:
            raise AssertionError(command)
        return self.pages[command[3]]

    def transaction(self, operation):
        return operation()


class CalibrationKeyboard(HECalibrationMixin):
    def __init__(self, transport):
        self.transport = transport

    def _write(self, commands):
        for command in commands:
            self.transport.send(command)
        self.transport.sleep(0.1)

    def _supported(self):
        return None

    def _check_commands(self, commands):
        return None


def test_read_calibration_exact_pages_and_little_endian_values():
    kb = CalibrationKeyboard(FakeTransport())
    result = kb.read_calibration()
    assert len(result["raw"]) == 512
    assert result["values"][:4] == [256, 256, 256, 256]
    assert result["values"][32] == 770


def test_calibration_start_wait_poll_stop_and_callback_phases():
    transport = FakeTransport()
    phases = []
    result = CalibrationKeyboard(transport).calibrate(1, phases.append)
    assert [command[:2] for command in transport.sent] == [
        bytes((0x1C, 1)),
        bytes((0x1C, 0)),
        bytes((0x1E, 1)),
        bytes((0x1E, 0)),
    ]
    assert [item["phase"] for item in phases][:2] == ["release", "press"]
    assert all(item["phase"] == "sample" for item in phases[2:])
    assert result["completed"] is True and result["samples"] == len(phases) - 2


@pytest.mark.parametrize("value", [True, False, 0, 301, float("inf"), float("nan"), "nope"])
def test_calibration_duration_bounds(value):
    with pytest.raises(ValueError):
        validate_duration(value)


def test_non_usb_is_rejected_before_writes():
    transport = FakeTransport()
    transport.kind = "bluetooth"
    with pytest.raises(UnsupportedDevice):
        CalibrationKeyboard(transport).calibrate()
    assert transport.sent == []


def test_start_failure_attempts_both_cleanup_commands():
    transport = FakeTransport()
    transport.fail_send = {1}
    with pytest.raises(OSError, match="send failure"):
        CalibrationKeyboard(transport).calibrate()
    assert [command[:2] for command in transport.sent] == [
        bytes((0x1C, 1)),
        bytes((0x1C, 0)),
        bytes((0x1E, 0)),
    ]


def test_cleanup_failure_reports_protocol_error_with_original_context():
    transport = FakeTransport()
    transport.fail_send = {1, 2}
    with pytest.raises(ProtocolError, match="cleanup failed"):
        CalibrationKeyboard(transport).calibrate()


def test_malformed_calibration_page_is_rejected():
    transport = FakeTransport()
    transport.pages[2] = b"short"
    with pytest.raises(ProtocolError):
        CalibrationKeyboard(transport).read_calibration()


def test_callback_cancellation_still_stops_calibration():
    transport = FakeTransport()

    def cancel(event):
        if event["phase"] == "press":
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        CalibrationKeyboard(transport).calibrate(30, cancel)
    assert [command[:2] for command in transport.sent][-2:] == [
        bytes((0x1C, 0)),
        bytes((0x1E, 0)),
    ]


@pytest.mark.parametrize("failure", [1, 2, 3, 4])
def test_each_start_or_stop_failure_attempts_independent_cleanup(failure):
    transport = FakeTransport()
    transport.fail_send = {failure}
    with pytest.raises(OSError, match="send failure"):
        CalibrationKeyboard(transport).calibrate(1)
    assert [c[:2] for c in transport.sent][-2:] == [b"\x1c\x00", b"\x1e\x00"]


def test_both_cleanup_failures_retain_original_error():
    transport = FakeTransport()
    transport.fail_send = {1, 2, 3}
    with pytest.raises(ProtocolError, match="cleanup failed") as error:
        CalibrationKeyboard(transport).calibrate(1)
    assert isinstance(error.value.__cause__, OSError)
    assert "1c: OSError" in str(error.value) and "1e: OSError" in str(error.value)
    assert len(transport.sent) == 3


@pytest.mark.parametrize("phase", ["release", "sample"])
def test_callback_cancellation_before_start_or_during_poll(phase):
    transport = FakeTransport()

    def cancel(event):
        if event["phase"] == phase:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        CalibrationKeyboard(transport).calibrate(1, cancel)
    if phase == "release":
        assert transport.sent == []
    else:
        assert [c[:2] for c in transport.sent][-2:] == [b"\x1c\x00", b"\x1e\x00"]


def test_telemetry_failure_stops_active_calibration():
    transport = FakeTransport()
    transport.pages[0] = b"bad"
    with pytest.raises(ProtocolError, match="64 bytes"):
        CalibrationKeyboard(transport).calibrate(1)
    assert [c[:2] for c in transport.sent][-2:] == [b"\x1c\x00", b"\x1e\x00"]


def test_session_and_page_reads_hold_transport_transaction():
    class Tracking(FakeTransport):
        depth = 0
        commands = []

        def transaction(self, operation):
            self.depth += 1
            try:
                return operation()
            finally:
                self.depth -= 1

        def send(self, command):
            assert self.depth >= 1
            self.commands.append((self.now, command))
            super().send(command)

        def exchange(self, command, **kwargs):
            assert self.depth >= 1
            return super().exchange(command, **kwargs)

    transport = Tracking()
    keyboard = CalibrationKeyboard(transport)
    keyboard.read_calibration()
    keyboard.calibrate(1)
    assert transport.depth == 0
    assert transport.commands[1][0] - transport.commands[0][0] >= 2
    assert all(
        len(command) == 64 and sum(command[:8]) % 256 == 255 for _, command in transport.commands
    )


@pytest.mark.parametrize("value", [None, [], 10**1000])
def test_bad_duration_types_and_huge_numbers(value):
    with pytest.raises(ValueError):
        validate_duration(value)


def test_noncallable_callback_is_rejected_without_write():
    transport = FakeTransport()
    with pytest.raises(ValueError, match="callable"):
        CalibrationKeyboard(transport).calibrate(1, on_progress=1)
    assert transport.sent == []
