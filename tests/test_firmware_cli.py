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
