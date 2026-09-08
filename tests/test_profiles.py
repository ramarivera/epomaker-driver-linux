import json
import zlib

import pytest

from epomaker_driver import profiles


def test_json_and_raw_deflate_roundtrip(tmp_path):
    value = {"schema": 1, "name": "Glyph α", "unknown": {"preserve": [1, 2, 3]}}
    assert profiles.decode(profiles.encode(value)) == value
    assert profiles.decode(profiles.encode(value, compressed=False)) == value
    path = tmp_path / "nested/profile.json"
    profiles.save(path, value)
    assert json.loads(path.read_text()) == value
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        profiles.save(path, {"new": 1})
    assert json.loads(path.read_text()) == value
    profiles.save(path, {"new": 1}, overwrite=True)
    assert json.loads(path.read_text()) == {"new": 1}
    assert not list(path.parent.glob(".profile.json*"))


@pytest.mark.parametrize("data", [b"bad", b"{bad", b'{"x":"\xff"}', b"[]", b"\x03"])
def test_invalid_profile(data):
    with pytest.raises(ValueError):
        profiles.decode(data)


def test_compression_limits(monkeypatch):
    monkeypatch.setattr(profiles, "MAX_PROFILE_BYTES", 64)
    with pytest.raises(ValueError):
        profiles.decode(b"x" * 65)
    with pytest.raises(ValueError):
        profiles.encode({"x": "x" * 65})
    compressor = zlib.compressobj(wbits=-15)
    bomb = compressor.compress(b" " * 10000) + compressor.flush()
    with pytest.raises(ValueError):
        profiles.decode(bomb)
    encoded = profiles.encode({"a": 1})
    with pytest.raises(ValueError):
        profiles.decode(encoded + b"trailing")
    with pytest.raises(ValueError):
        profiles.decode(encoded[:-1])
    with pytest.raises(ValueError):
        profiles.encode([])
    compressor = zlib.compressobj(wbits=-15)
    data = compressor.compress(b"[]") + compressor.flush()
    with pytest.raises(ValueError):
        profiles.decode(data)
