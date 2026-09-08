"""Mouse macro and semantic binding CLI round trips."""

import json

import pytest
from test_mouse_cli import install

from epomaker_driver import cli, macros


@pytest.mark.parametrize("model", [3961, 3303, 3304, 3929, 3919])
def test_mouse_macro_json_upload_readback_and_binding(monkeypatch, capsys, tmp_path, model):
    _, fw, info = install(monkeypatch, model)
    definition = {
        "repeat": 3,
        "events": [
            {"hid_usage": 4, "down": True, "delay_ms": 127},
            {"type": "mouse_button", "button": "forward", "down": False, "delay_ms": 128},
            {"type": "mouse_move", "dx": -127, "dy": 127, "delay_ms": 5},
        ],
    }
    path = tmp_path / "macro.json"
    path.write_text(json.dumps(definition))
    prefix = ["--device", info.path]
    assert cli.main(prefix + ["macro", "49", str(path)]) == 0
    capsys.readouterr()
    assert fw.macros[49] == macros.encode(**definition)
    assert cli.main(prefix + ["get-macro", "49", "--decoded"]) == 0
    assert json.loads(capsys.readouterr().out) == definition
    assert cli.main(prefix + ["get-macro", "49"]) == 0
    assert bytes.fromhex(json.loads(capsys.readouterr().out)["data"]) == fw.macros[49]
    assert cli.main(prefix + ["bind-macro", "0", "49", "--mode", "held"]) == 0
    assert fw.matrix[0, 0] == bytes.fromhex("09023100")


@pytest.mark.parametrize(
    "command,expected",
    [
        (["bind-key", "0", "a", "--modifier", "ctrl", "--second", "b"], "00010405"),
        (["bind-media", "0", "volume-up"], "0300e900"),
        (["bind-mouse", "0", "wheel-up"], "0100f700"),
        (["mouse-bind", "0", "scroll-up"], "0100f501"),
        (["mouse-bind", "0", "dpi-down"], "00020014"),
        (["disable-key", "0"], "00000000"),
    ],
)
def test_mouse_named_bindings_have_exact_wire_bytes(monkeypatch, capsys, command, expected):
    _, fw, info = install(monkeypatch, 3961)
    prefix = ["--device", info.path]
    assert cli.main(prefix + command) == 0
    assert fw.matrix[0, 0].hex() == expected
    capsys.readouterr()
    assert cli.main(prefix + ["mouse-matrix"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["slots"][0] == expected
    assert result["bindings"][0]["raw"] == expected


@pytest.mark.parametrize("flag", [["--fn"], ["--os-mode", "1"], ["--submode", "1"]])
def test_keyboard_banks_rejected_before_mouse_binding_write(monkeypatch, capsys, flag):
    _, fw, info = install(monkeypatch, 3961)
    assert cli.main(["--device", info.path, "bind-key", "0", "a"] + flag) == 1
    assert "error" in capsys.readouterr().err
    assert not fw.sent


def test_mouse_macro_ambiguous_decode_does_not_lose_raw(monkeypatch, capsys):
    _, fw, info = install(monkeypatch, 3961)
    fw.macros[0] = bytes.fromhex("0100f9010101") + bytes(250)
    prefix = ["--device", info.path, "get-macro", "0"]
    assert cli.main(prefix + ["--decoded"]) == 1
    assert "compact" in capsys.readouterr().err
    assert cli.main(prefix) == 0
    assert json.loads(capsys.readouterr().out)["data"] == fw.macros[0].hex()


def test_malformed_macro_file_rejected_before_hid_open(monkeypatch, capsys, tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text('{"repeat":1,"events":[{"hid_usage":4,"down":true,"delay_ms":0}]}')
    monkeypatch.setattr(cli.Transport, "open", lambda _: pytest.fail("must not open HID"))
    assert cli.main(["macro", "0", str(path)]) == 1
    assert "zero-delay" in capsys.readouterr().err


@pytest.mark.parametrize("slot", ["-1", "50", "255"])
def test_mouse_macro_binding_rejects_unallocated_slots(monkeypatch, capsys, slot):
    _, fw, info = install(monkeypatch, 3961)
    assert cli.main(["--device", info.path, "bind-macro", "0", slot]) == 1
    assert "0..49" in capsys.readouterr().err
    assert not fw.sent
