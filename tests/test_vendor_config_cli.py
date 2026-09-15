import json
import zlib

import pytest

from epomaker_driver import cli, profiles


@pytest.mark.parametrize("compressed", [False, True])
def test_preview_is_offline_and_resolves_macro_binding(tmp_path, capsys, monkeypatch, compressed):
    monkeypatch.setattr(cli, "discover", lambda: pytest.fail("preview must not discover hardware"))
    monkeypatch.setattr(
        cli.Transport, "open", lambda *args: pytest.fail("preview must not open HID")
    )
    path = tmp_path / "vendor.dat"
    record = {
        "deviceType": {"id": 3059},
        "fn": False,
        "value": [
            {
                "original": 4,
                "index": 0,
                "type": "ConfigMacro",
                "macroType": "on_off",
                "macroIndex": 7,
                "macro": [],
            }
        ],
    }
    path.write_bytes(profiles.encode(record, compressed=compressed))
    assert cli.main(["preview-vendor-config", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["write_ready"] is False
    assert result["macro_slots"] == [7]
    assert result["macro_payload_actions"] == [0]
    assert len(bytes.fromhex(result["matrix"])) == 512
    assert not (tmp_path / "backup").exists()


def test_fn_requires_explicit_target_even_with_gzip(tmp_path, capsys):
    record = {"deviceType": {"id": 3059}, "fn": True, "value": []}
    compressor = zlib.compressobj(wbits=31)
    path = tmp_path / "fn.gz"
    path.write_bytes(compressor.compress(json.dumps(record).encode()) + compressor.flush())
    assert cli.main(["preview-vendor-config", str(path)]) == 1
    assert "target" in capsys.readouterr().err.lower()
    assert cli.main(["preview-vendor-config", str(path), "--target", "Fn Mac"]) == 0
    assert json.loads(capsys.readouterr().out)["target"] == "Fn Mac"
