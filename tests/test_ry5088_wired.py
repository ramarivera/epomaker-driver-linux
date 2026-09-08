import json

import pytest
from test_he import Firmware, keyboard

from epomaker_driver import cli, codec
from epomaker_driver.discovery import Collection, DeviceInfo, Report, classify
from epomaker_driver.errors import UnsupportedDevice
from epomaker_driver.models import data_file

MODELS = [
    (2465, 0x5029),
    (2586, 0x502D),
    (2870, 0x502D),
    (3691, 0x5030),
    (3692, 0x5030),
    (3703, 0x5030),
    (2761, 0x5030),
    (2959, 0x5030),
]


@pytest.mark.parametrize("model,product", MODELS)
def test_wired_model_cli_profile3_submode3_and_switch_gate(model, product, monkeypatch, capsys):
    fw = Firmware(model_id=model)
    info = DeviceInfo("/dev/wired", "Keyboard", 3, 0x3151, product, b"", "usb", 0)

    class Opened:
        def __enter__(self):
            return keyboard(fw, product=product).transport

        def __exit__(self, *_):
            return None

    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: Opened())
    assert cli.main(["--device", info.path, "identify"]) == 0
    assert json.loads(capsys.readouterr().out)["device_id"] == model
    assert (
        cli.main(
            ["--device", info.path, "key", "1", "00000400", "--profile", "3", "--submode", "3"]
        )
        == 0
    )
    capsys.readouterr()
    assert fw.sent[-1] == codec.single_key(3, 1, bytes.fromhex("00000400"), mode=3, profile_max=3)
    assert fw.matrices[3, 3][4:8] == bytes.fromhex("00000400")
    fw.sent.clear()
    result = cli.main(["--device", info.path, "switch-type", "33", "1"])
    assert result == (0 if model in (2465, 2761) else 1)
    capsys.readouterr()
    assert bool(fw.sent) == (model in (2465, 2761))
    assert cli.main(["--device", info.path, "switch-type", "5", "1"]) == 0
    capsys.readouterr()
    assert fw.fields[252][1] == 5


@pytest.mark.parametrize("model,product", MODELS)
def test_fn_maps_respect_catalog_os_banks(model, product):
    fw = Firmware(model_id=model)
    kb = keyboard(fw, product=product)
    action = bytes.fromhex("00000400")
    kb.set_key(1, action, fn=True)
    assert kb.read_matrix(fn=True)[4:8] == action
    before = len(fw.sent)
    if model in (2586, 2761):
        with pytest.raises(UnsupportedDevice, match="Fn bank"):
            kb.read_matrix(fn=True, os_mode=1)
        with pytest.raises(UnsupportedDevice, match="Fn bank"):
            kb.set_key(1, action, fn=True, os_mode=1)
        assert len(fw.sent) == before
    else:
        kb.set_key(1, action, fn=True, os_mode=1)
        assert kb.read_matrix(fn=True, os_mode=1)[4:8] == action


@pytest.mark.parametrize("model,product", MODELS)
def test_model_specific_snap_restoration_and_precision(model, product):
    fw = Firmware(model_id=model)
    fw.usb_version = 0x500
    kb = keyboard(fw, product=product)
    kb.set_profile(3)
    kb.set_magnetic(1, {"travel": 2.005})
    assert fw.fields[0][2:4] == (401).to_bytes(2, "little")
    kb.set_snap(1, 2)
    kb.clear_snap(1)
    default = bytes(data_file("he60-matrices.json")[str(model)]["defaultMatrix"])
    for slot in (1, 2):
        assert fw.matrices[3, 0][slot * 4 : slot * 4 + 4] == default[slot * 4 : slot * 4 + 4]
        for submode in (1, 2, 3):
            assert fw.matrices[3, submode][slot * 4 : slot * 4 + 4] == bytes(4)
    assert fw.fields[0][2:4] == (401).to_bytes(2, "little")


@pytest.mark.parametrize(
    "model,product",
    [
        (2465, 0x502D),
        (2586, 0x5029),
        (2870, 0x5030),
        (3691, 0x5029),
        (2550, 0x502D),
        (3883, 0x5030),
    ],
)
def test_wrong_pid_or_unmigrated_sibling_cannot_write(model, product):
    fw = Firmware(model_id=model)
    with pytest.raises(UnsupportedDevice):
        keyboard(fw, product=product).set_key(1, bytes(4))
    assert fw.sent == []


@pytest.mark.parametrize("pid", [0x502D, 0x5030])
def test_new_products_need_exact_feature_collection(pid):
    report = Report(0, feature_bits=512, collections={Collection(0xFFFF, 2)})
    assert classify(3, 0x3151, pid, {0: report}) == ("usb", 0)
    assert classify(3, 0x3151, pid, {0: Report(0, feature_bits=512)}) == (None, None)
    assert classify(5, 0x3151, pid, {0: report}) == (None, None)
