"""Scalar mouse settings through the USB transport, with independent firmware state."""

import copy

import pytest
from test_mouse import USB, MouseFirmware
from test_mouse_cli import install

from epomaker_driver import cli
from epomaker_driver.errors import ProtocolError, UnsupportedDevice
from epomaker_driver.mouse import Mouse
from epomaker_driver.transport import Transport


class SettingsFirmware(MouseFirmware):
    # Explicit opcodes and widths from CH585 vendor methods, not the Linux codec table.
    fields = {
        4: ("debounce", 1),
        5: ("scroll_up_time", 1),
        6: ("sleep_24", 2),
        7: ("sleep_bt", 2),
        17: ("lod", 1),
        18: ("line_repair", 1),
        19: ("wave_repair", 1),
        12: ("low_latency", 1),
    }

    def __init__(self, model_id=3961):
        super().__init__(model_id)
        self.values = dict(
            debounce=5,
            scroll_up_time=20,
            sleep_24=300,
            sleep_bt=600,
            lod=0,
            line_repair=0,
            wave_repair=0,
            low_latency=0,
        )
        self.drop_setting = False
        self.change_profile = False

    def exchange(self, command):
        if command[0] - 128 in self.fields:
            self.query_log.append(bytes(command))
            name, width = self.fields[command[0] - 128]
            return (
                bytes([command[0]])
                + self.values[name].to_bytes(width, "little")
                + bytes(63 - width)
            )
        return super().exchange(command)

    def send(self, command):
        if command[0] in self.fields:
            self.sent.append(bytes(command))
            assert sum(command[:8]) & 255 == 255
            name, width = self.fields[command[0]]
            assert command[1 + width : 7] == bytes(6 - width)
            assert command[8:] == bytes(56)
            if not self.drop_setting:
                self.values[name] = int.from_bytes(command[1 : 1 + width], "little")
            if self.change_profile:
                self.profile = 1
        else:
            super().send(command)


def device(model=3961):
    fw = SettingsFirmware(model)
    transport = Transport(USB(fw), "usb", sleep=lambda _: None)
    return Mouse(transport, product_id=fw.product_id), fw


@pytest.mark.parametrize("model", [3961, 3303, 3304, 3929, 3919])
@pytest.mark.parametrize(
    "name,value",
    [
        ("debounce", 1),
        ("debounce", 10),
        ("scroll_up_time", 1),
        ("scroll_up_time", 255),
        ("sleep_24", 0),
        ("sleep_24", 65535),
        ("sleep_bt", 0),
        ("sleep_bt", 65535),
        ("line_repair", True),
        ("wave_repair", True),
    ],
)
def test_scalar_roundtrip_preserves_every_other_setting(model, name, value):
    mouse, fw = device(model)
    before = copy.deepcopy(fw.values)
    result = mouse.set_setting(name, value)
    before[name] = int(value)
    assert fw.values == before
    assert result == {"setting": name, "value": value, "profile": 0}
    assert len(fw.sent) == 1
    mouse.set_setting(name, value)
    assert len(fw.sent) == 1  # Verified no-op sends no configuration write.


@pytest.mark.parametrize("model,last", [(3961, 2), (3304, 2), (3929, 1)])
def test_lod_is_zero_based_sensor_index(model, last):
    mouse, fw = device(model)
    assert mouse.set_setting("lod", last)["value"] == last
    with pytest.raises(ValueError):
        mouse.set_setting("lod", last + 1)
    assert len(fw.sent) == 1


@pytest.mark.parametrize("model", [3303, 3919])
def test_lod_hidden_for_sensors_without_vendor_selector(model):
    mouse, fw = device(model)
    with pytest.raises(UnsupportedDevice):
        mouse.set_setting("lod", 0)
    assert not fw.sent


@pytest.mark.parametrize(
    "model,version,enabled",
    [
        (3929, 0x0799, False),
        (3929, 0x0800, True),
        (3929, 0x07FF, False),
        (3929, 0, False),
        (3919, 0x0099, False),
        (3919, 0x0100, True),
        (3961, 0x9999, False),
        (3303, 0x9999, False),
        (3304, 0x9999, False),
    ],
)
def test_low_latency_uses_vendor_display_version_gate(model, version, enabled):
    mouse, fw = device(model)
    fw.usb_version = version
    mouse.identify()
    assert mouse.setting_options()["low_latency"] is enabled
    if enabled:
        assert mouse.set_setting("low_latency", 1)["value"] == 1
    else:
        with pytest.raises(UnsupportedDevice):
            mouse.set_setting("low_latency", 1)
        assert not fw.sent


@pytest.mark.parametrize("failure", ["drop_setting", "change_profile"])
def test_setting_readback_and_profile_change_fail(failure):
    mouse, fw = device()
    setattr(fw, failure, True)
    with pytest.raises(ProtocolError):
        mouse.set_setting("debounce", 2)


def test_profile_race_before_write(monkeypatch):
    mouse, fw = device()
    profiles = iter([0, 1])
    monkeypatch.setattr(mouse, "get_profile", lambda: next(profiles))
    with pytest.raises(ProtocolError, match="before"):
        mouse.set_setting("debounce", 2)
    assert not fw.sent


def test_mutation_reidentifies_device():
    mouse, fw = device()
    mouse.identify()
    fw.model_id = 3303
    with pytest.raises(UnsupportedDevice):
        mouse.set_setting("debounce", 2)
    assert not fw.sent


def test_bt_catalog_hide_gate(monkeypatch):
    mouse, fw = device()
    mouse.identify()
    mouse.model = copy.deepcopy(mouse.model)
    mouse.model.setdefault("other", {})["noShowBT"] = True
    monkeypatch.setattr(mouse, "identify", lambda: mouse.identity)
    with pytest.raises(UnsupportedDevice):
        mouse.set_setting("sleep_bt", 10)
    assert not fw.sent


@pytest.mark.parametrize(
    "name,value",
    [
        ("debounce", "10"),
        ("scroll_up_time", "255"),
        ("sleep_24", "65535"),
        ("sleep_bt", "0"),
        ("lod", "2"),
        ("line_repair", "1"),
        ("wave_repair", "1"),
    ],
)
def test_cli_settings(monkeypatch, capsys, name, value):
    _, _, info = install(monkeypatch, 3961)
    mouse, fw = device()
    monkeypatch.setattr(
        cli.Transport,
        "open",
        lambda _: Transport(USB(fw), "usb", sleep=lambda _: None),
    )
    prefix = ["--device", info.path, "mouse-setting", name]
    assert cli.main(prefix + [value]) == 0
    assert cli.main(prefix) == 0
    assert not capsys.readouterr().err
    assert fw.values[name] == int(value)


def test_cli_rejects_nonboolean_value(monkeypatch, capsys):
    _, fw, info = install(monkeypatch, 3961)
    assert cli.main(["--device", info.path, "mouse-setting", "line_repair", "2"]) == 1
    assert "0 or 1" in capsys.readouterr().err
    assert not fw.sent


@pytest.mark.parametrize(
    "name,old,new",
    [("debounce", 255, 3), ("scroll_up_time", 0, 4), ("lod", 255, 1), ("low_latency", 255, 0)],
)
def test_raw_out_of_ui_values_remain_readable_and_repairable(name, old, new):
    mouse, fw = device(3929)
    fw.usb_version = 0x0800
    fw.values[name] = old
    assert mouse.get_setting(name) == old
    assert mouse.set_setting(name, new)["value"] == new
