"""Private, atomic persistence for named Glyph macro drafts."""

from __future__ import annotations

import fcntl
import os
import re
import uuid
from contextlib import contextmanager
from pathlib import Path

from . import macros, profiles

_ID = re.compile(r"^[0-9a-f]{32}$")
_MODES = {"count", "toggle", "held"}
MAX_ENTRY_BYTES = 1024 * 1024
MAX_ENTRIES = 4096


def _id(value):
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError("macro library id must be 32 lowercase hexadecimal characters")
    return value


def _revision(value):
    if type(value) is not int or value < 1:
        raise ValueError("macro library revision must be a positive integer")
    return value


def _value(value):
    if type(value) is not dict or set(value) != {"repeat", "events"}:
        raise ValueError("macro library value must contain exactly repeat and events")
    repeat, events = value["repeat"], value["events"]
    # Let the protocol encoder enforce numeric bounds and event semantics first.
    macros.encode(repeat, events)
    normalized = []
    for event in events:
        clean = dict(event)
        if clean.get("type") == "keyboard":
            clean.pop("type")
        normalized.append(clean)
    return {"repeat": repeat, "events": normalized}


def _entry(value):
    if type(value) is not dict or set(value) != {"id", "revision", "name", "mode", "value"}:
        raise ValueError("macro library entry has unexpected fields")
    ident = _id(value["id"])
    revision = _revision(value["revision"])
    name = value["name"]
    if type(name) is not str:
        raise ValueError("macro library name must be text")
    name = name.strip()
    if not name:
        raise ValueError("macro library name must not be blank")
    if len(name) > 20:
        raise ValueError("macro library name must be at most 20 Unicode codepoints")
    mode = value["mode"]
    if type(mode) is not str or mode not in _MODES:
        raise ValueError("macro library mode must be count, toggle, or held")
    return {
        "id": ident,
        "revision": revision,
        "name": name,
        "mode": mode,
        "value": _value(value["value"]),
    }


class MacroLibrary:
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
                raise ValueError("macro library entry exceeds size limit")
            entry = _entry(profiles.decode(raw))
            if entry["id"] != path.stem:
                raise ValueError("filename id does not match entry id")
            return entry
        except ValueError as error:
            raise ValueError(f"invalid macro library entry {path.name}: {error}") from error

    def _entries(self):
        paths = sorted(self.directory.glob("*.json"))
        if len(paths) > MAX_ENTRIES:
            raise ValueError("macro library contains too many entries")
        return [self._read(path) for path in paths]

    def list(self):
        if not self.directory.exists():
            return []
        with self._locked():
            return self._entries()

    def save(self, name, value, mode, ident=None, revision=None):
        if ident is None and revision is not None:
            raise ValueError("revision requires an existing macro library id")
        clean_name = name.strip() if type(name) is str else name
        candidate = {
            "id": ident or uuid.uuid4().hex,
            "revision": 1 if ident is None else revision,
            "name": clean_name,
            "mode": mode,
            "value": value,
        }
        if ident is None:
            _entry(candidate)
        else:
            _id(ident)
            _revision(revision)
        with self._locked():
            path = self._path(candidate["id"])
            if ident is None:
                if len(self._entries()) >= MAX_ENTRIES:
                    raise ValueError("macro library contains too many entries")
                entry = _entry(candidate)
                try:
                    profiles.save(path, entry)
                except FileExistsError:
                    raise ValueError("macro library id already exists; retry") from None
                return entry
            if not path.is_file():
                raise ValueError("macro library entry does not exist")
            current = self._read(path)
            if current["revision"] != revision:
                raise ValueError("macro library revision conflict")
            entry = _entry(
                {
                    "id": ident,
                    "revision": revision + 1,
                    "name": clean_name,
                    "mode": mode,
                    "value": value,
                }
            )
            profiles.save(path, entry, overwrite=True)
            return entry

    def delete(self, ident, revision):
        _id(ident)
        _revision(revision)
        with self._locked():
            path = self._path(ident)
            if not path.is_file():
                raise ValueError("macro library entry does not exist")
            current = self._read(path)
            if current["revision"] != revision:
                raise ValueError("macro library revision conflict")
            path.unlink()
            return {"ok": True}
