"""Private, atomic persistence for named offline Glyph display assets."""

from __future__ import annotations

import base64
import binascii
import fcntl
import os
import re
import uuid
from contextlib import contextmanager
from pathlib import Path

from . import media, profiles

_ID = re.compile(r"^[0-9a-f]{32}$")
MODEL_ID = 3059
VERSION = 1
MAX_DECODED_BYTES = 14 * 1024 * 1024
MAX_ENCODED_BYTES = 4 * ((MAX_DECODED_BYTES + 2) // 3)
MAX_ENTRY_BYTES = 20 * 1024 * 1024
MAX_ENTRIES = 256


def _id(value):
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError("display asset id must be 32 lowercase hexadecimal characters")
    return value


def _name(value):
    if type(value) is not str:
        raise ValueError("display asset name must be text")
    value = value.strip()
    if not value:
        raise ValueError("display asset name must not be blank")
    if len(value) > 80:
        raise ValueError("display asset name must be at most 80 Unicode codepoints")
    return value


def _content(value):
    if type(value) is not str or not value:
        raise ValueError("display asset content must be canonical base64")
    if len(value) > MAX_ENCODED_BYTES:
        raise ValueError("display asset content exceeds the 14 MiB limit")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("display asset content must be canonical base64") from error
    if not raw or len(raw) > MAX_DECODED_BYTES:
        raise ValueError("display asset content exceeds the 14 MiB limit")
    canonical = base64.b64encode(raw).decode("ascii")
    if canonical != value:
        raise ValueError("display asset content must be canonical base64")
    return raw


def _entry(value):
    fields = {
        "id",
        "name",
        "kind",
        "delay_ms",
        "frame_count",
        "pixel_bytes",
        "content",
        "model_id",
        "version",
    }
    if type(value) is not dict or set(value) != fields:
        raise ValueError("display asset entry has unexpected fields")
    ident = _id(value["id"])
    name = _name(value["name"])
    kind = value["kind"]
    if kind not in ("screen", "animation"):
        raise ValueError("display asset kind must be screen or animation")
    delay = value["delay_ms"]
    if kind == "screen":
        if delay is not None:
            raise ValueError("still display assets must have null delay")
        frame_limit = (1, 1)
    elif type(delay) is not int or not 0 <= delay <= 255:
        raise ValueError("animation delay must be an integer in 0..255")
    else:
        frame_limit = (2, 46)
    frame_count = value["frame_count"]
    if type(frame_count) is not int or not frame_limit[0] <= frame_count <= frame_limit[1]:
        raise ValueError("display asset frame_count is outside the supported range")
    pixel_bytes = value["pixel_bytes"]
    if type(pixel_bytes) is not int or pixel_bytes != frame_count * 121552:
        raise ValueError("display asset pixel_bytes does not match frame_count")
    if type(value["model_id"]) is not int or value["model_id"] != MODEL_ID:
        raise ValueError("unsupported display asset model or version")
    if type(value["version"]) is not int or value["version"] != VERSION:
        raise ValueError("unsupported display asset model or version")
    _content(value["content"])
    return dict(value, id=ident, name=name)


class DisplayLibrary:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.lock_path = self.directory / ".lock"

    @contextmanager
    def _locked(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(fd, "r+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _path(self, ident):
        _id(ident)
        return self.directory / f"{ident}.json"

    def _read(self, path):
        try:
            if not _ID.fullmatch(path.stem):
                raise ValueError("filename must be a lowercase 32-hex id")
            with path.open("rb") as stream:
                raw = stream.read(MAX_ENTRY_BYTES + 1)
            if len(raw) > MAX_ENTRY_BYTES:
                raise ValueError("display asset entry exceeds size limit")
            entry = _entry(profiles.decode(raw))
            if entry["id"] != path.stem:
                raise ValueError("filename id does not match entry id")
            return entry
        except ValueError as error:
            raise ValueError(f"invalid display asset entry {path.name}: {error}") from error

    def _entries(self):
        paths = sorted(self.directory.glob("*.json"))
        if len(paths) > MAX_ENTRIES:
            raise ValueError("display library contains too many entries")
        for path in paths:
            yield self._read(path)

    @staticmethod
    def _public(entry):
        return {
            key: entry[key]
            for key in ("id", "name", "kind", "delay_ms", "frame_count", "pixel_bytes")
        }

    def list(self):
        if not self.directory.exists():
            return []
        with self._locked():
            return [self._public(entry) for entry in self._entries()]

    def save(self, name, kind, delay_ms, content):
        name = _name(name)
        if kind == "screen" and delay_ms is not None:
            raise ValueError("still display assets must have null delay")
        raw = _content(content)
        prepared = media.prepare_display(raw, kind=kind, delay_ms=delay_ms, model_id=MODEL_ID)
        entry = {
            "id": uuid.uuid4().hex,
            "name": name,
            "kind": kind,
            "delay_ms": prepared["delay_ms"],
            "frame_count": prepared["frame_count"],
            "pixel_bytes": prepared["pixel_bytes"],
            "content": base64.b64encode(raw).decode("ascii"),
            "model_id": MODEL_ID,
            "version": VERSION,
        }
        entry = _entry(entry)
        with self._locked():
            if sum(1 for _ in self._entries()) >= MAX_ENTRIES:
                raise ValueError("display library contains too many entries")
            try:
                profiles.save(self._path(entry["id"]), entry)
            except FileExistsError:
                raise ValueError("display asset id already exists; retry") from None
        return self._public(entry)

    def get(self, ident):
        with self._locked():
            entry = self._read(self._path(ident))
        raw = _content(entry["content"])
        prepared = media.prepare_display(
            raw, kind=entry["kind"], delay_ms=entry["delay_ms"], model_id=MODEL_ID
        )
        for key in ("delay_ms", "frame_count", "pixel_bytes"):
            if prepared[key] != entry[key]:
                raise ValueError(f"display asset metadata mismatch for {key}")
        return {**entry, "preview_png": prepared["preview_png"]}

    def delete(self, ident):
        _id(ident)
        with self._locked():
            path = self._path(ident)
            if not path.is_file():
                raise ValueError("display asset does not exist")
            self._read(path)
            path.unlink()
        return {"ok": True}
