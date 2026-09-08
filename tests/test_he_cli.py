"""CLI dispatch checks; actual USB transactions are covered in test_he.py."""

import json

import pytest

from epomaker_driver import cli
from epomaker_driver.discovery import DeviceInfo


@pytest.fixture(params=[0x502C, 0x502E])
def he_cli(request, monkeypatch, firmware):
    info = DeviceInfo(
        "/dev/hidraw60",
        "HE60 Lite",
        3,
        0x3151,
        request.param,
        bytes.fromhex("06ffff0902a10175089540b102c0"),
        "usb",
        0,
    )
    calls = []

    class Backend:
        def __init__(self, transport, *, product_id):
            assert transport is firmware and product_id == request.param

        def get_magnetic(self):
            calls.append("magnetic")
            return {"profile": 1, "fields": {"7": "80" * 128}}

        def read_matrix(self, profile, **options):
            calls.append(("matrix", profile, options))
            return bytes([0, 0, 5, 0]) * 128

        def set_key(self, slot, action, **options):
            calls.append(("key", slot, bytes(action), options))
            return list(action)

    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: firmware)
    monkeypatch.setattr(cli, "HEKeyboard", Backend)
    return ["--device", info.path], calls


def test_he_cli_submodes_and_magnetic_query(he_cli, capsys):
    prefix, calls = he_cli
    assert cli.main([*prefix, "get-magnetic"]) == 0
    assert json.loads(capsys.readouterr().out)["fields"]["7"] == "80" * 128
    assert calls[-1] == "magnetic"
    assert cli.main([*prefix, "matrix", "--profile", "1", "--submode", "3"]) == 0
    assert json.loads(capsys.readouterr().out)["slots"] == [[0, 0, 5, 0]] * 128
    assert calls[-1] == ("matrix", 1, {"fn": False, "os_mode": 0, "mode": 3})
    assert cli.main([*prefix, "key", "9", "00000600", "--profile", "1", "--submode", "2"]) == 0
    capsys.readouterr()
    assert calls[-1] == (
        "key",
        9,
        b"\x00\x00\x06\x00",
        {"profile": 1, "fn": False, "os_mode": 0, "mode": 2},
    )
    assert cli.main([*prefix, "disable-key", "8", "--submode", "1"]) == 0
    capsys.readouterr()
    assert calls[-1] == (
        "key",
        8,
        bytes(4),
        {"profile": 0, "fn": False, "os_mode": 0, "mode": 1},
    )


def test_he_unmigrated_command_rejects_before_open(he_cli, monkeypatch, capsys):
    prefix, calls = he_cli
    monkeypatch.setattr(cli.Transport, "open", lambda _: pytest.fail("must reject before open"))
    assert cli.main([*prefix, "clock"]) == 1
    assert "has not been migrated" in capsys.readouterr().err
    assert not calls


@pytest.mark.parametrize(
    "command",
    [["get-magnetic"], ["matrix", "--submode", "1"], ["magnetic-key", "0", "--travel", "1.2"]],
)
def test_non_he_rejects_magnetic_commands_before_open(command, monkeypatch, capsys):
    info = DeviceInfo("/dev/hidraw1", "RT100 PRO", 3, 0x3151, 0x5002, b"", "usb", 0)
    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: pytest.fail("must reject before open"))
    assert cli.main(["--device", info.path, *command]) == 1
    assert "require HE60 Lite" in capsys.readouterr().err
