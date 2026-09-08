"""Sleep and RF gates for the additional RY5088 wireless models."""

import pytest
from test_he import Firmware, keyboard
from test_he_settings import state

from epomaker_driver import cli, codec
from epomaker_driver.discovery import DeviceInfo
from epomaker_driver.errors import ProtocolError, UnsupportedDevice
from epomaker_driver.he_settings import plan_update

WIRELESS = (3692, 3703, 2761, 2959)


def make_keyboard(firmware):
    kb = keyboard(firmware, product=0x5030)
    if firmware.model_id in (3703, 2959):
        firmware.side_light = bytearray(codec.light("solid", side=True))
        exchange = firmware.exchange
        send = firmware.send

        def side_exchange(_self, command):
            if command[0] == 0x88:
                return bytes([0x88]) + bytes(firmware.side_light[1:])
            return exchange(command)

        def side_send(_self, command):
            if command[0] == 8:
                firmware.side_light = bytearray(command)
                firmware.sent.append(command)
                return
            send(command)

        from types import MethodType

        firmware.exchange = MethodType(side_exchange, firmware)
        firmware.send = MethodType(side_send, firmware)
    return kb


@pytest.mark.parametrize("model_id", WIRELESS)
def test_5030_models_identify_and_expose_rf_and_three_public_sleep_timers(model_id):
    firmware = Firmware(model_id=model_id)
    kb = make_keyboard(firmware)

    value = kb.status()
    assert value["identity"]["device_id"] == model_id
    assert value["versions"]["rf"] == 0x0500
    assert value["sleep"] == {
        "bluetooth": 60,
        "dongle": 60,
        "deep_bluetooth": 60,
    }
    assert "deep_dongle" not in value["sleep"]


@pytest.mark.parametrize("model_id", WIRELESS)
def test_5030_sleep_preserves_hidden_deep_dongle_word(model_id):
    firmware = Firmware(model_id=model_id)
    firmware.sleep[3] = 0xBEEF
    kb = keyboard(firmware, product=0x5030)

    assert kb.set_sleep(0, 64800, 10) == {
        "bluetooth": 0,
        "dongle": 64800,
        "deep_bluetooth": 10,
    }
    command = firmware.sent[-1]
    assert command[0] == 0x11
    assert command[8:16] == bytes.fromhex("000020fd0a00efbe")
    assert firmware.sleep == [0, 64800, 10, 0xBEEF]


@pytest.mark.parametrize("values", [(0, 0, 9), (64801, 0, 10), (0, 64801, 10), (0, 0, 64801)])
def test_5030_sleep_rejects_out_of_range_values_before_write(values):
    firmware = Firmware(model_id=3692)
    kb = make_keyboard(firmware)
    before = len(firmware.sent)
    with pytest.raises(ValueError):
        kb.set_sleep(*values)
    assert len(firmware.sent) == before


@pytest.mark.parametrize("bad", [(0, 0, 10, 1), (False, 0, 10), ("0", 0, 10), (-1, 0, 10)])
def test_5030_sleep_rejects_hidden_or_malformed_public_values_before_write(bad):
    firmware = Firmware(model_id=3692)
    kb = keyboard(firmware, product=0x5030)
    with pytest.raises(ValueError):
        kb.set_sleep(*bad)
    assert not firmware.sent


@pytest.mark.parametrize("model_id", WIRELESS)
@pytest.mark.parametrize("failure", ["write", "hidden"])
def test_5030_sleep_detects_write_and_hidden_word_readback_failures(model_id, failure):
    firmware = Firmware(model_id=model_id)
    if failure == "write":
        firmware.drop_sleep_write = True
    else:
        firmware.corrupt_sleep_hidden = True
    kb = make_keyboard(firmware)
    with pytest.raises(ProtocolError, match="sleep|hidden"):
        kb.set_sleep(0, 64800, 10)


@pytest.mark.parametrize(
    "rf_version, multiplier, travel, raw", [(0x0300, 100, 2.01, 201), (0x0500, 200, 2.01, 402)]
)
def test_5030_rf_version_precedes_usb_for_actuation_encoding(rf_version, multiplier, travel, raw):
    current = state(usb=0x0500, rf=rf_version, travel=2.0)
    result = plan_update(3692, 0, {"travel": travel}, current)
    assert result["changed_fields"] == [0]
    assert bytes.fromhex(result["expected_fields"]["0"])[:2] == raw.to_bytes(2, "little")
    assert current["versions"] == {"usb": 0x0500, "rf": rf_version}
    if rf_version == 0x0300:
        with pytest.raises(ValueError):
            plan_update(3692, 0, {"travel": 2.005}, current)


@pytest.mark.parametrize("model_id", WIRELESS)
def test_5030_cli_sleep_uses_real_pid_and_three_public_values(monkeypatch, capsys, model_id):
    firmware = Firmware(model_id=model_id)
    info = DeviceInfo(f"/dev/ry5088-{model_id}", "RY5088", 3, 0x3151, 0x5030, b"", "usb", 0)

    class Opened:
        def __enter__(self):
            return make_keyboard(firmware).transport

        def __exit__(self, *_):
            return None

    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: Opened())
    assert cli.main(["--device", info.path, "sleep", "0", "64800", "10"]) == 0
    capsys.readouterr()
    assert firmware.sleep[:3] == [0, 64800, 10]
    assert firmware.sleep[3] == 65535


def test_3691_wired_rejects_sleep_and_rf_commands():
    firmware = Firmware(model_id=3691)
    kb = keyboard(firmware, product=0x5030)
    with pytest.raises(UnsupportedDevice):
        kb.get_sleep()
    assert kb.status()["versions"]["rf"] is None
    assert "sleep" not in kb.status()
    with pytest.raises(UnsupportedDevice):
        kb._check_commands([codec.packet([0x80])])
    with pytest.raises(UnsupportedDevice):
        kb._check_commands([codec.packet([0x11])])
    assert not any(command[0] in (0x11, 0x91, 0x80) for command in firmware.query_log)
    assert not any(command[0] in (0x11, 0x91, 0x80) for command in firmware.sent)


@pytest.mark.parametrize("model_id", WIRELESS)
@pytest.mark.parametrize("rf_version, multiplier", [(0, 200), (0x0300, 100), (0x0500, 200)])
def test_5030_rf_version_drives_magnetic_scaling(model_id, rf_version, multiplier):
    firmware = Firmware(model_id=model_id)
    firmware.usb_version = 0x0500
    firmware.rf_version = rf_version
    kb = keyboard(firmware, product=0x5030)
    value = kb.get_magnetic()
    assert value["versions"]["rf"] == (rf_version or None)
    assert value["multiplier"] == multiplier
    assert any(command[0] == 0x80 for command in firmware.query_log)
    kb.set_magnetic(1, {"travel": 2.01})
    raw = (201 if multiplier == 100 else 402).to_bytes(2, "little")
    assert firmware.fields[0][2:4] == raw
    command = firmware.sent[-1]
    assert command[:5] == bytes([0x65, 0, 0, 1, 1])
    assert command[8:10] == raw
    if rf_version == 0x0300:
        before = len(firmware.sent)
        with pytest.raises(ValueError):
            kb.set_magnetic(1, {"travel": 2.005})
        assert len(firmware.sent) == before


def test_2761_rejects_mac_fn_bank_from_catalog_metadata():
    firmware = Firmware(model_id=2761)
    kb = keyboard(firmware, product=0x5030)
    with pytest.raises(UnsupportedDevice):
        kb.read_matrix(fn=True, os_mode=1)
    assert not any(command[0] == 0x90 for command in firmware.query_log)
