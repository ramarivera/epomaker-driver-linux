import json

import pytest

from epomaker_driver import cli, profiles, snapshot
from epomaker_driver.device import Keyboard
from epomaker_driver.models import glyph_matrix


@pytest.mark.parametrize("compressed", [False, True])
def test_export_from_snapshot_is_offline_and_no_clobber(
    firmware, tmp_path, capsys, monkeypatch, compressed
):
    firmware.matrices[0][:] = glyph_matrix()
    firmware.matrices[0][0:4] = bytes([0, 1, 5, 0])
    source = tmp_path / "snapshot.json"
    profiles.save(source, snapshot.capture(Keyboard(firmware)))
    destination = tmp_path / "vendor.dat"
    monkeypatch.setattr(cli, "select_device", lambda _: pytest.fail("export must be offline"))
    args = ["export-vendor-config", str(source), str(destination), "--name", "My Glyph"]
    if compressed:
        args.append("--compressed")
    assert cli.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["action_count"] == 1
    raw = destination.read_bytes()
    record = profiles.decode(raw)
    assert record["name"] == "My Glyph"
    assert raw.startswith(b"{") is not compressed
    assert destination.stat().st_mode & 0o777 == 0o600
    assert cli.main(args) == 1
    assert "FileExistsError" in capsys.readouterr().err
    assert destination.read_bytes() == raw
    assert not firmware.sent


def test_unrepresentable_export_creates_no_output(firmware, tmp_path, capsys):
    firmware.matrices[0][:] = glyph_matrix()
    firmware.matrices[0][114 * 4 : 115 * 4] = bytes(4)
    source = tmp_path / "snapshot.json"
    profiles.save(source, snapshot.capture(Keyboard(firmware)))
    destination = tmp_path / "vendor.json"
    assert cli.main(["export-vendor-config", str(source), str(destination)]) == 1
    assert not destination.exists()
    assert capsys.readouterr().err
