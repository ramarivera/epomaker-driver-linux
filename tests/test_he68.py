"""HE68 Lite family (RY5088 IDs 2762, 2883, 3664) integration tests."""

import pytest
from test_he import Firmware, keyboard

from epomaker_driver import cli, codec
from epomaker_driver.discovery import DeviceInfo
from epomaker_driver.errors import ProtocolError, UnsupportedDevice
from epomaker_driver.models import data_file

HE68 = (2762, 2883, 3664)


@pytest.mark.parametrize("model", HE68)
def test_he68_identity_profile3_fn_and_shared_pid(model):
    fw = Firmware(model_id=model)
    kb = keyboard(fw, product=0x5029)
    assert kb.identify()["device_id"] == model
    assert "magnetic-axis-read" in kb.status()["capabilities"]
    assert kb.read_matrix(profile=3, mode=3)[:2] == bytes((3, 3))
    kb.set_key(5, b"\0\0\x06\0", profile=3, mode=3)
    assert fw.matrices[(3, 3)][20:24] == b"\0\0\x06\0"
    assert kb.read_matrix(profile=0, fn=True, os_mode=1)[:2] == b"\0\1"
    assert kb.read_macro(7) == bytes(256)
    assert kb.get_light()["raw"][0] == 0x87
    assert kb.read_picture(4) == bytes([4]) * 378


@pytest.mark.parametrize("model", HE68)
def test_he68_axis_field_full_read_preserves_unknown_values(model):
    fw = Firmware(model_id=model)
    raw = bytearray((index * 37) & 255 for index in range(128))
    raw[0] = 255
    raw[1] = 0
    fw.fields[252] = bytes(raw)
    kb = keyboard(fw, product=0x5029)
    state = kb.get_magnetic()
    assert state["fields"]["252"] == bytes(raw).hex()
    assert all(isinstance(slot["axis_type"], int) for slot in state["slots"])
    assert state["slots"][0]["axis_type"] == 255


@pytest.mark.parametrize("model", HE68)
def test_he68_mode_and_snap_clear_at_profile3(model):
    fw = Firmware(model_id=model)
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
    fw.fields[7] = bytes(
        0x07 if index in (1, 2) else value for index, value in enumerate(fw.fields[7])
    )
    fw.fields[9] = bytes(2 if index == 1 else 1 if index == 2 else 0 for index in range(128))
    result = kb.clear_snap(1)
    assert result["profile"] == 3
    default = bytes(data_file("he60-matrices.json")[str(model)]["defaultMatrix"])
    for slot in (1, 2):
        assert fw.matrices[3, 0][slot * 4 : slot * 4 + 4] == default[slot * 4 : slot * 4 + 4]
        for submode in (1, 2, 3):
            assert fw.matrices[3, submode][slot * 4 : slot * 4 + 4] == bytes(4)
    assert all(c[1] == 3 for c in fw.sent if c[0] == 0x0A)


def test_he68_sibling_2465_is_rejected_before_writes():
    fw = Firmware(model_id=2465)
    kb = keyboard(fw, product=0x5029)
    with pytest.raises(UnsupportedDevice):
        kb.identify()
    assert fw.sent == []


@pytest.mark.parametrize("model", HE68)
def test_he68_cli_high_precision_write_preserves_switch_types(model, monkeypatch, capsys):
    fw = Firmware(model_id=model)
    fw.usb_version = 0x500
    fw.fields[3] = bytes([100, 0]) * 128
    axes = bytes([255, 0, 4, 6] * 32)
    fw.fields[252] = axes
    info = DeviceInfo("/dev/he68", "HE68", 3, 0x3151, 0x5029, b"", "usb", 0)

    class Opened:
        def __enter__(self):
            return keyboard(fw, product=0x5029).transport

        def __exit__(self, *_):
            return None

    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: Opened())
    assert cli.main(["--device", info.path, "identify"]) == 0
    assert str(model) in capsys.readouterr().out
    assert cli.main(["--device", info.path, "magnetic-key", "0", "--rapid-press", "0.005"]) == 0
    capsys.readouterr()
    assert fw.fields[252] == axes
    assert fw.sent[-1] == codec.packet([0x65, 2, 0, 0, 1, 0, 0, 0, 1, 0])
    assert not any(c[0] == 0x65 and c[1] == 252 for c in fw.sent)


@pytest.mark.parametrize("model", HE68)
def test_he68_axis_damage_is_detected_during_actuation_readback(model):
    class Damaging(Firmware):
        def send(self, command):
            super().send(command)
            if command[0] == 0x65:
                self.fields[252] = b"\xff" + self.fields[252][1:]

    fw = Damaging(model_id=model)
    fw.fields[252] = bytes(128)
    kb = keyboard(fw, product=0x5029)
    with pytest.raises(ProtocolError, match="readback"):
        kb.set_magnetic(0, {"travel": 2.01})


@pytest.mark.parametrize("model", HE68)
@pytest.mark.parametrize("product,boot", [(0x5029, True), (0x502C, False), (0x502E, False)])
def test_he68_wrong_product_and_bootloader_are_rejected(model, product, boot):
    fw = Firmware(model_id=model, boot=boot)
    kb = keyboard(fw, product=product)
    with pytest.raises(UnsupportedDevice):
        kb.set_key(1, bytes(4))
    assert fw.sent == []


def test_shared_pid_cached_identity_cannot_bypass_approved_ids():
    fw = Firmware(model_id=2762)
    kb = keyboard(fw, product=0x5029)
    kb.identify()
    kb.identity["device_id"] = kb.expected_id = 2465
    with pytest.raises(UnsupportedDevice):
        kb.set_key(1, bytes(4))
    assert fw.sent == []
