"""Portable local profiles and bounded raw-DEFLATE vendor JSON import."""

from __future__ import annotations

import json
import os
import tempfile
import zlib
from pathlib import Path

MAX_PROFILE_BYTES = 8 * 1024 * 1024


def decode(data: bytes) -> dict:
    if len(data) > MAX_PROFILE_BYTES:
        raise ValueError("profile exceeds size limit")
    if data.lstrip().startswith(b"{"):
        raw = data
    else:
        decoder = zlib.decompressobj(-15)
        try:
            raw = decoder.decompress(data, MAX_PROFILE_BYTES + 1)
        except zlib.error as error:
            raise ValueError("profile is neither JSON nor raw DEFLATE") from error
        if len(raw) > MAX_PROFILE_BYTES or decoder.unconsumed_tail:
            raise ValueError("decompressed profile exceeds size limit")
        if not decoder.eof or decoder.unused_data:
            raise ValueError("profile stream is truncated or has trailing data")
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise ValueError("invalid profile JSON") from error
    if not isinstance(value, dict):
        raise ValueError("profile must be an object")
    return value


def encode(value: dict, *, compressed=True) -> bytes:
    if not isinstance(value, dict):
        raise ValueError("profile must be an object")
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
    if len(raw) > MAX_PROFILE_BYTES:
        raise ValueError("profile exceeds size limit")
    if not compressed:
        return raw
    encoder = zlib.compressobj(wbits=-15)
    return encoder.compress(raw) + encoder.flush()


def save(path: Path, value: dict, *, overwrite=False):
    """Atomic user-private write; no temporary partially readable profiles."""
    path = Path(path)
    raw = encode(value, compressed=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)  # atomic no-clobber, including symlinks
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
