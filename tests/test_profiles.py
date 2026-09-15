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


@pytest.mark.parametrize("wbits", [15, 31, -15])
@pytest.mark.parametrize("level", [0, 1, 6, 9])
def test_vendor_compression_wrappers(wbits, level):
    value = {"name": "Glyph 漢", "value": [0, 1, 2, 255]}
    compressor = zlib.compressobj(level=level, wbits=wbits)
    encoded = compressor.compress(json.dumps(value).encode()) + compressor.flush()
    assert profiles.decode(encoded) == value


@pytest.mark.parametrize("wbits", [15, 31])
def test_wrapped_stream_rejects_truncation_trailing_data_and_bad_checksum(wbits):
    compressor = zlib.compressobj(wbits=wbits)
    encoded = compressor.compress(b'{"name":"Glyph"}') + compressor.flush()
    for invalid in (
        encoded[:-1],
        encoded + b"trailing",
        encoded + encoded,
        encoded[:-1] + bytes([encoded[-1] ^ 255]),
    ):
        with pytest.raises(ValueError):
            profiles.decode(invalid)


@pytest.mark.parametrize("wbits", [15, 31])
def test_wrapped_expansion_limits(monkeypatch, wbits):
    compressor = zlib.compressobj(wbits=wbits)
    encoded = compressor.compress(b'{"name":"' + b"x" * 10000 + b'"}') + compressor.flush()
    monkeypatch.setattr(profiles, "MAX_PROFILE_BYTES", 128)
    assert len(encoded) < profiles.MAX_PROFILE_BYTES
    with pytest.raises(ValueError, match="decompressed profile exceeds"):
        profiles.decode(encoded)
