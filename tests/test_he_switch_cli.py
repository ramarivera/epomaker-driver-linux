import json

import pytest
from test_he import Firmware, keyboard

from epomaker_driver import cli, codec
from epomaker_driver.discovery import DeviceInfo


def install(monkeypatch, fw, product=0x5029):
    info = DeviceInfo("/dev/switch", "Keyboard", 3, 0x3151, product, b"", "usb", 0)

    class Opened:
        def __enter__(self):
            return keyboard(fw, product=product).transport

        def __exit__(self, *_):
            return None

    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: Opened())
    return info.path


@pytest.mark.parametrize("model", (2762, 2883, 3664))
@pytest.mark.parametrize("selection", ("冰玉", "33"))
def test_named_and_numeric_switch_cli_multi_key(model, selection, monkeypatch, capsys):
    fw = Firmware(model_id=model)
    fw.fields[252] = bytes([255]) * 128
    path = install(monkeypatch, fw)
    assert cli.main(["--device", path, "switch-type", selection, "1", "2"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["changed"] and result["axis_type"] == 33
    assert result["slots"] == [1, 2]
    assert fw.sent == [codec.packet([0x65, 252, 0, slot, 1, 0, 0, 0, 33]) for slot in (1, 2)]
    assert fw.fields[252] == bytes([255, 33, 33]) + bytes([255]) * 125
    assert cli.main(["--device", path, "status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert "switch-type" in status["capabilities"]
    assert status["switch_types"]["冰玉"] == 33


def test_nonmagnetic_switch_cli_rejected_before_open(monkeypatch, capsys):
    info = DeviceInfo("/dev/other", "Other", 3, 0x3151, 0x5002, b"", "usb", 0)
    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: pytest.fail("must reject before open"))
    assert cli.main(["--device", info.path, "switch-type", "33", "1"]) == 1
    assert "UnsupportedDevice" in capsys.readouterr().err


@pytest.mark.parametrize("model,product", [(3662, 0x5029), (3727, 0x502C), (3759, 0x502E)])
def test_nonreplaceable_model_switch_cli_rejected_without_write(
    model, product, monkeypatch, capsys
):
    fw = Firmware(model_id=model)
    path = install(monkeypatch, fw, product)
    assert cli.main(["--device", path, "switch-type", "33", "1"]) == 1
    assert "UnsupportedDevice" in capsys.readouterr().err
    assert not fw.sent


@pytest.mark.parametrize("selection", ["6", "255", "unknown", "-1"])
def test_invalid_selection_is_rejected_before_device_open(selection, monkeypatch):
    monkeypatch.setattr(cli, "discover", lambda: pytest.fail("must validate before discovery"))
    with pytest.raises(SystemExit) as error:
        cli.main(["switch-type", selection, "1"])
    assert error.value.code == 2
