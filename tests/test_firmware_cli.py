import json
import zlib

import pytest

from epomaker_driver import cli, firmware


def test_inspection_offline(tmp_path, capsys, monkeypatch):
    image = bytes(65536) + b"payload"
    packed = zlib.compress(image, wbits=-15)
    path = tmp_path / "firmware.bin"
    path.write_bytes(packed)
    monkeypatch.setattr(cli, "select_device", lambda _: pytest.fail("must remain offline"))
    assert cli.main(["inspect-firmware", str(path), "--version", "v1"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == firmware.inspect_container(packed, version="v1")
    assert result["write_ready"] is False
    assert path.read_bytes() == packed


def test_input_limit_and_missing_file(tmp_path, capsys, monkeypatch):
    path = tmp_path / "oversized.bin"
    monkeypatch.setattr(firmware, "MAX_SIZE", 16)
    path.write_bytes(bytes(17))
    assert cli.main(["inspect-firmware", str(path), "--version", "v1"]) == 1
    assert capsys.readouterr().err
    path.unlink()
    assert cli.main(["inspect-firmware", str(path), "--version", "v1"]) == 1
    assert "FileNotFoundError" in capsys.readouterr().err


def test_cli_version_comparison(tmp_path, capsys):
    path = tmp_path / "image"
    path.write_bytes(zlib.compress(bytes(65536) + b"payload", wbits=-15))
    current = tmp_path / "versions.json"
    current.write_text('{"usb":256}')
    args = [
        "inspect-firmware",
        str(path),
        "--version",
        "v1.0.2",
        "--current-versions",
        str(current),
    ]
    assert cli.main(args) == 0
    item = json.loads(capsys.readouterr().out)["version_comparison"]["candidates"][0]
    assert item["observed"] == 258 and item["candidate"] is True
    current.write_bytes(bytes(4097))
    assert cli.main(args) == 1
    assert "4096" in capsys.readouterr().err
    current.write_text("not json")
    assert cli.main(args) == 1
    assert capsys.readouterr().err
