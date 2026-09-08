import hashlib
import json
from types import SimpleNamespace

import pytest
from test_mouse import mouse_keyboard

from epomaker_driver import cli, mouse_cli
from epomaker_driver.discovery import Collection, DeviceInfo, Report, classify
from epomaker_driver.models import data_file


def install(monkeypatch, model):
    mouse, fw = mouse_keyboard(model)
    info = DeviceInfo("/dev/mouse", "Mouse", 3, 0x3151, mouse.product_id, b"", "usb", 0)

    class Opened:
        def __enter__(self):
            return mouse.transport

        def __exit__(self, *_):
            return None

    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: Opened())
    return mouse, fw, info


@pytest.mark.parametrize("model", [3961, 3303, 3304, 3929, 3919])
def test_mouse_cli_workflows_dispatch_to_mouse_namespace(monkeypatch, capsys, model):
    mouse, fw, info = install(monkeypatch, model)
    prefix = ["--device", info.path]
    for command in (
        ["identify"],
        ["status"],
        ["get-mouse-settings"],
        ["profile", "7"],
        ["mouse-matrix", "--profile", "7"],
        ["mouse-key", "0", "0100f000", "--profile", "7"],
        ["get-mouse-dpi", "--profile", "7"],
        [
            "mouse-dpi",
            "--profile",
            "7",
            "--slot",
            "1",
            "--x",
            "1600",
            "--y",
            "1600",
            "--rgb",
            "ff0000",
        ],
        ["mouse-rate", "1000"],
    ):
        assert cli.main(prefix + command) == 0
        assert isinstance(json.loads(capsys.readouterr().out), dict)
    assert fw.matrix[7, 0] == bytes.fromhex("0100f000")
    assert any(c[0] == 0x10 and c[1] == 7 for c in fw.sent)
    assert fw.sent[-1][:2] == bytes([8, 1])
    assert mouse.identify()["usb_version"] == 0x0400


@pytest.mark.parametrize(
    "mouse_device,command",
    [
        (True, ["light", "wave"]),
        (True, ["get-magnetic"]),
        (False, ["mouse-rate", "1000"]),
        (False, ["mouse-dpi", "--current", "1"]),
    ],
)
def test_mouse_keyboard_commands_cannot_cross_namespaces(
    monkeypatch, capsys, mouse_device, command
):
    info = DeviceInfo(
        "/dev/test", "Test", 3, 0x3151, 0x503A if mouse_device else 0x5002, b"", "usb", 0
    )
    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(
        cli.Transport, "open", lambda _: pytest.fail("must reject before opening HID")
    )
    assert cli.main(["--device", info.path] + command) == 1
    assert "UnsupportedDevice" in capsys.readouterr().err


@pytest.mark.parametrize("pid", [0x503A, 0x5043])
def test_mouse_discovery_requires_exact_usb_feature_descriptor(pid):
    report = Report(0, feature_bits=512, collections={Collection(0xFFFF, 2)})
    assert classify(3, 0x3151, pid, {0: report}) == ("usb", 0)
    assert classify(5, 0x3151, pid, {0: report}) == (None, None)
    assert classify(3, 0x3151, pid, {0: Report(0, feature_bits=512)}) == (None, None)
    assert classify(
        3, 0x3151, pid, {0: Report(0, feature_bits=504, collections={Collection(0xFFFF, 2)})}
    ) == (None, None)
    assert classify(3, 0x3151, pid + 1, {0: report}) == (None, None)


def test_mouse_matrices_match_both_installer_hashes():
    hashes = {
        3961: "0bbde583f1b5cc53495d5f61ea01446ee83be2eb123da7a70038f27646fdc2e0",
        3303: "19a38ea6f085c69ef347c46a560206d964c23d4b88d10eea4d4494b20ad5fe3a",
        3304: "19a38ea6f085c69ef347c46a560206d964c23d4b88d10eea4d4494b20ad5fe3a",
        3929: "3a00af39bf2c322e9a48c824d5c828fa108ecbacac25d2df57f9762b2ab3708d",
        3919: "0bbde583f1b5cc53495d5f61ea01446ee83be2eb123da7a70038f27646fdc2e0",
    }
    matrices = data_file("ch585-matrices.json")
    assert set(matrices) == set(map(str, hashes))
    for mid, digest in hashes.items():
        raw = bytes(matrices[str(mid)])
        assert len(raw) == 64
        assert hashlib.sha256(raw).hexdigest() == digest


def test_mouse_dispatch_rejects_unknown_command():
    with pytest.raises(ValueError):
        mouse_cli.run(None, SimpleNamespace(command="unknown"))
