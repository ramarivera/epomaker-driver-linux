import json

import pytest
from test_he import Firmware, keyboard

from epomaker_driver import cli
from epomaker_driver.discovery import DeviceInfo


class CalibrationFirmware(Firmware):
    def __init__(self, model):
        super().__init__(model_id=model)
        self.fields[254] = b"".join(value.to_bytes(2, "little") for value in range(128))

    def send(self, command):
        if command[0] in (0x1C, 0x1E):
            self.sent.append(bytes(command))
        else:
            super().send(command)


def install(monkeypatch, model, *, cancel=False):
    fw = CalibrationFirmware(model)
    product = {
        3727: 0x502C,
        3759: 0x502E,
        2586: 0x502D,
        2870: 0x502D,
        3691: 0x5030,
        3692: 0x5030,
        3703: 0x5030,
        2761: 0x5030,
        2959: 0x5030,
        3365: 0x5030,
        4071: 0x5030,
        3417: 0x5030,
        3518: 0x5054,
        3613: 0x5054,
        3883: 0x5030,
    }.get(model, 0x5029)
    info = DeviceInfo("/dev/calibration", "Keyboard", 3, 0x3151, product, b"", "usb", 0)
    now = [0.0]

    def sleep(delay):
        if cancel and delay == 2:
            raise KeyboardInterrupt
        now[0] += delay

    class Opened:
        def __enter__(self):
            transport = keyboard(fw, product=product).transport
            transport.clock = lambda: now[0]
            transport.sleep = sleep
            return transport

        def __exit__(self, *_):
            return None

    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: Opened())
    return fw, info.path


@pytest.mark.parametrize(
    "model",
    (
        3662,
        3664,
        2762,
        2883,
        3727,
        3759,
        2465,
        2586,
        2870,
        3691,
        3692,
        3703,
        2761,
        2959,
        3746,
        3365,
        4071,
        3417,
        3518,
        3613,
        3883,
    ),
)
def test_calibration_cli_orders_start_stop_and_reports_raw_readings(model, monkeypatch, capsys):
    fw, path = install(monkeypatch, model)
    assert cli.main(["--device", path, "calibrate", "--seconds", "1"]) == 0
    output = capsys.readouterr()
    assert "Release all keys" in output.err and "Press every key" in output.err
    data = json.loads(output.out)
    assert data["completed"] and data["samples"] > 0
    assert data["last"]["values"] == list(range(128))
    assert [c[:2] for c in fw.sent] == [b"\x1c\x01", b"\x1c\x00", b"\x1e\x01", b"\x1e\x00"]
    assert cli.main(["--device", path, "read-calibration"]) == 0
    assert json.loads(capsys.readouterr().out)["values"] == list(range(128))
    assert len(fw.sent) == 4


def test_calibration_cli_ctrl_c_stops_both_phases(monkeypatch, capsys):
    fw, path = install(monkeypatch, 2762, cancel=True)
    assert cli.main(["--device", path, "calibrate", "--seconds", "1"]) == 130
    assert "interrupted" in capsys.readouterr().err
    assert [c[:2] for c in fw.sent] == [b"\x1c\x01", b"\x1c\x00", b"\x1e\x00"]


@pytest.mark.parametrize("seconds", ("0", "301", "nan", "inf", "bad"))
def test_bad_calibration_duration_is_rejected_before_discovery(seconds, monkeypatch):
    monkeypatch.setattr(cli, "discover", lambda: pytest.fail("must reject before discovery"))
    with pytest.raises(SystemExit) as error:
        cli.main(["calibrate", "--seconds", seconds])
    assert error.value.code == 2


@pytest.mark.parametrize("command", ("calibrate", "read-calibration"))
def test_calibration_nonmagnetic_rejected_before_open(command, monkeypatch, capsys):
    info = DeviceInfo("/dev/other", "Other", 3, 0x3151, 0x5002, b"", "usb", 0)
    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: pytest.fail("must reject before open"))
    assert cli.main(["--device", info.path, command]) == 1
    assert "UnsupportedDevice" in capsys.readouterr().err
