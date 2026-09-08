"""H60 (RY5088 ID 3662) integration and model-gate checks."""

import pytest
from test_he import Firmware, keyboard

from epomaker_driver import cli, codec
from epomaker_driver.discovery import Collection, DeviceInfo, Report, classify
from epomaker_driver.errors import UnsupportedDevice
from epomaker_driver.he_settings import plan_update
from epomaker_driver.models import data_file


def test_h60_cli_matrix_and_key_use_profile3_submode3(monkeypatch, capsys):
    fw = Firmware(model_id=3662)
    info = DeviceInfo("/dev/h60", "H60", 3, 0x3151, 0x5029, b"", "usb", 0)

    class Opened:
        def __enter__(self):
            return keyboard(fw, product=0x5029).transport

        def __exit__(self, *_):
            return None

    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: Opened())
    assert cli.main(["--device", info.path, "matrix", "--profile", "3", "--submode", "3"]) == 0
    capsys.readouterr()
    assert any(c[0] == 0x8A and c[1] == 3 and c[4] == 3 for c in fw.query_log)
    assert (
        cli.main(
            ["--device", info.path, "key", "5", "00000600", "--profile", "3", "--submode", "3"]
        )
        == 0
    )
    capsys.readouterr()
    writes = [c for c in fw.sent if c[0] == 0x0A]
    assert writes[-1][1] == 3 and writes[-1][2] == 5 and writes[-1][6] == 3
    assert writes[-1][8:12] == bytes.fromhex("00000600")


def test_h60_status_capabilities_have_no_sleep_or_debounce():
    fw = Firmware(model_id=3662)
    status = keyboard(fw, product=0x5029).status()
    assert status["profiles"] == 4
    assert status["picture_banks"] == 5
    assert len(status["capabilities"]) == len(set(status["capabilities"]))
    assert {"magnetic-read", "magnetic-actuation", "magnetic-modes", "snap"} <= set(
        status["capabilities"]
    )
    assert "sleep" not in status and "debounce" not in status
    assert "magnetic-axis-read" not in status["capabilities"]


def test_h60_same_pid_sibling_rejected_before_io():
    fw = Firmware(model_id=2465)
    kb = keyboard(fw, product=0x5029)
    with pytest.raises(UnsupportedDevice):
        kb.status()
    assert fw.sent == []


def test_h60_magnetic_mode_and_snap_clear_use_profile3():
    fw = Firmware(model_id=3662)
    kb = keyboard(fw, product=0x5029)
    kb.identify()
    kb.set_profile(3)
    kb.set_magnetic_mode(
        5,
        {
            "mode": "dks",
            "actions": ["00000400", "00000500", "00000600", "00000700"],
            "dynamic_travel": 0.7,
            "trigger_modes": [1, 2, 3, 4],
        },
    )
    fw.fields[7] = bytes((0x07 if i in (1, 2) else value) for i, value in enumerate(fw.fields[7]))
    fw.fields[9] = bytes(2 if i == 1 else 1 if i == 2 else 0 for i in range(128))
    result = kb.clear_snap(1)
    assert result["profile"] == 3
    default = bytes(data_file("he60-matrices.json")["3662"]["defaultMatrix"])
    for slot in (1, 2):
        assert fw.matrices[3, 0][slot * 4 : slot * 4 + 4] == default[slot * 4 : slot * 4 + 4]
        for submode in (1, 2, 3):
            assert fw.matrices[3, submode][slot * 4 : slot * 4 + 4] == bytes(4)
        assert fw.fields[7][slot] & 0x7F == 0
    writes = [c for c in fw.sent if c[0] == 0x0A]
    assert all(c[1] == 3 for c in writes)
    assert {c[6] for c in writes} == {0, 1, 2, 3}


def test_h60_descriptor_requires_expected_collection_and_report():
    report = Report(0, feature_bits=512, collections={Collection(0xFFFF, 2)})
    assert classify(3, 0x3151, 0x5029, {0: report}) == ("usb", 0)
    assert classify(
        3, 0x3151, 0x5029, {0: Report(0, feature_bits=504, collections=report.collections)}
    ) == (
        None,
        None,
    )
    assert classify(3, 0x3151, 0x5029, {0: Report(0, feature_bits=64)}) == (None, None)


def _state(usb, *, mode=0):
    multiplier = 10 if usb < 0x300 else 100 if usb < 0x500 else 200

    def u16(value):
        return int(value * multiplier).to_bytes(2, "little")

    fields = {str(field): bytes(256).hex() for field in (0, 1, 2, 3, 6)}
    fields["0"] = (u16(2.0) + bytes(254)).hex()
    fields["1"] = (u16(0.5) + bytes(254)).hex()
    fields["2"] = (u16(0.5) + bytes(254)).hex()
    fields["3"] = (u16(0.6) + bytes(254)).hex()
    fields["6"] = (u16(0.2) + bytes(254)).hex()
    fields["7"] = bytes([0x80 if mode == 0 else mode]).hex() + bytes(127).hex()
    return {
        "fields": fields,
        "modes": [0x80 if mode == 0 else mode] + [0] * 127,
        "versions": {"usb": usb, "rf": None},
    }


@pytest.mark.parametrize("usb,value", [(0x500, 0.005), (0x400, 0.01), (0x200, 2.5)])
def test_h60_rapid_trigger_precision_and_old_limit(usb, value):
    result = plan_update(3662, 0, {"rapid_press": value}, _state(usb))
    assert result["changed_fields"] == [2]
    raw = 25 if usb == 0x200 else 1
    assert result["commands"] == [codec.packet([0x65, 2, 0, 0, 1, 0, 0, 0, raw, 0])]
    assert bytes.fromhex(result["expected_fields"]["2"])[:2] == bytes([raw, 0])


def test_h60_travel_minimum_and_stale_invalid_rapid_are_rejected():
    with pytest.raises(ValueError):
        plan_update(3662, 0, {"travel": 0.005}, _state(0x500))
    state = _state(0x500)
    state["modes"][0] = 0
    state["fields"]["7"] = bytes(128).hex()
    state["fields"]["2"] = (bytes([0xFF, 0xFF]) + bytes(254)).hex()
    with pytest.raises(ValueError):
        plan_update(3662, 0, {"fire": True}, state)


@pytest.mark.parametrize("usb,rapid", [(0x500, 0.005), (0x400, 0.01), (0x200, 2.5)])
def test_h60_rapid_write_roundtrip_preserves_other_slots(usb, rapid):
    fw = Firmware(model_id=3662)
    fw.usb_version = usb
    kb = keyboard(fw, product=0x5029)
    baseline = dict(fw.fields)
    result = kb.set_magnetic(5, {"fire": True, "rapid_press": rapid, "rapid_lift": rapid})
    assert result["changed"]
    assert fw.fields[7][5] == 0x80
    for field in (2, 3):
        raw = 25 if usb == 0x200 else 1
        assert fw.fields[field][10:12] == bytes([raw, 0])
        assert fw.fields[field][:10] == baseline[field][:10]
        assert fw.fields[field][12:] == baseline[field][12:]


@pytest.mark.parametrize(
    "call",
    [
        lambda kb: kb.set_key(5, bytes(4), profile=4),
        lambda kb: kb.set_key(5, bytes(4), profile=3, mode=4),
        lambda kb: kb.set_key(5, bytes(4), profile=1, fn=True),
        lambda kb: kb.set_debounce(1),
        lambda kb: kb.set_sleep(60, 60, 60),
        lambda kb: kb.set_magnetic(5, {"travel": 0.005}),
    ],
)
def test_h60_invalid_or_absent_controls_never_write(call):
    fw = Firmware(model_id=3662)
    fw.usb_version = 0x500
    kb = keyboard(fw, product=0x5029)
    with pytest.raises((ValueError, UnsupportedDevice)):
        call(kb)
    assert fw.sent == []
