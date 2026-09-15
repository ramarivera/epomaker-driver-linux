"""Private, atomic persistence for named Glyph key configurations."""

from __future__ import annotations

import fcntl
import os
import re
import uuid
from contextlib import contextmanager
from pathlib import Path

from . import profiles

_ID = re.compile(r"^[0-9a-f]{32}$")
_MATRIX = re.compile(r"^[0-9a-fA-F]{1024}$")
_LAYERS = {"Main", "Fn Windows", "Fn Mac"}
MODEL_ID = 3059
MAX_ENTRY_BYTES = 1024 * 1024
MAX_ENTRIES = 4096


def _id(value):
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError("config library id must be 32 lowercase hexadecimal characters")
    return value


def _revision(value):
    if type(value) is not int or value < 1:
        raise ValueError("config library revision must be a positive integer")
    return value


def _name(value):
    if type(value) is not str:
        raise ValueError("config library name must be text")
    value = value.strip()
    if not value:
        raise ValueError("config library name must not be blank")
    if len(value) > 20:
        raise ValueError("config library name must be at most 20 Unicode codepoints")
    return value


def _matrix(value):
    if type(value) is not str or not _MATRIX.fullmatch(value):
        raise ValueError("config library matrix must be exactly 1024 hexadecimal characters")
    return value.lower()


def _layer(value):
    if type(value) is not str or value not in _LAYERS:
        raise ValueError("config library layer must be Main, Fn Windows, or Fn Mac")
    return value


def _model(value):
    if type(value) is not int or value != MODEL_ID:
        raise ValueError("unsupported config library model")
    return value


def _entry(value):
    fields = {"id", "revision", "name", "model_id", "matrix", "layer"}
    if type(value) is not dict or set(value) != fields:
        raise ValueError("config library entry has unexpected fields")
    return {
        "id": _id(value["id"]),
        "revision": _revision(value["revision"]),
        "name": _name(value["name"]),
        "model_id": _model(value["model_id"]),
        "matrix": _matrix(value["matrix"]),
        "layer": _layer(value["layer"]),
    }


class ConfigLibrary:
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
                raise ValueError("config library entry exceeds size limit")
            entry = _entry(profiles.decode(raw))
            if entry["id"] != path.stem:
                raise ValueError("filename id does not match entry id")
            return entry
        except ValueError as error:
            raise ValueError(f"invalid config library entry {path.name}: {error}") from error

    def _entries(self):
        paths = sorted(self.directory.glob("*.json"))
        if len(paths) > MAX_ENTRIES:
            raise ValueError("config library contains too many entries")
        return [self._read(path) for path in paths]

    def list(self):
        if not self.directory.exists():
            return []
        with self._locked():
            return self._entries()

    def get(self, ident, revision):
        _id(ident)
        _revision(revision)
        with self._locked():
            path = self._path(ident)
            if not path.is_file():
                raise ValueError("config library entry does not exist")
            entry = self._read(path)
            if entry["revision"] != revision:
                raise ValueError("config library revision conflict")
            return entry

    def save(self, name, matrix, layer, ident=None, revision=None):
        if ident is None and revision is not None:
            raise ValueError("revision requires an existing config library id")
        candidate = {
            "id": ident or uuid.uuid4().hex,
            "revision": 1 if ident is None else revision,
            "name": name,
            "model_id": MODEL_ID,
            "matrix": matrix,
            "layer": layer,
        }
        if ident is None:
            entry = _entry(candidate)
        else:
            _id(ident)
            _revision(revision)
        with self._locked():
            path = self._path(candidate["id"])
            if ident is None:
                if len(self._entries()) >= MAX_ENTRIES:
                    raise ValueError("config library contains too many entries")
                try:
                    profiles.save(path, entry)
                except FileExistsError:
                    raise ValueError("config library id already exists; retry") from None
                return entry
            if not path.is_file():
                raise ValueError("config library entry does not exist")
            current = self._read(path)
            if current["revision"] != revision:
                raise ValueError("config library revision conflict")
            entry = _entry({**candidate, "revision": revision + 1})
            profiles.save(path, entry, overwrite=True)
            return entry

    def delete(self, ident, revision):
        _id(ident)
        _revision(revision)
        with self._locked():
            path = self._path(ident)
            if not path.is_file():
                raise ValueError("config library entry does not exist")
            current = self._read(path)
            if current["revision"] != revision:
                raise ValueError("config library revision conflict")
            path.unlink()
            return {"ok": True}
