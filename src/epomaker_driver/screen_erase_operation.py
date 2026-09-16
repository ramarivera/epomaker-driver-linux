"""Journaled, one-shot vendor screen erase operation."""

from __future__ import annotations

import json
import math
import threading
import time
import uuid
from pathlib import Path

from . import profiles

MAX_JOURNAL_BYTES = 64 * 1024
_STATES = {"idle", "running", "completed", "uncertain", "acknowledged"}


class ScreenEraseOperation:
    def __init__(self, path, *, clock=time.monotonic):
        self.path = Path(path)
        self.clock = clock
        self._lock = threading.RLock()
        self._worker = None
        self._cancel = None
        self._started = None
        self._state = self._idle()
        self._load()

    @staticmethod
    def _idle():
        return {
            "operation_id": None,
            "state": "idle",
            "active": False,
            "blocked": False,
            "elapsed_seconds": 0.0,
            "completion_received": False,
            "error": None,
            "target_session": None,
        }

    @staticmethod
    def _validate(value):
        if type(value) is not dict or set(value) != set(ScreenEraseOperation._idle()):
            raise ValueError("screen erase journal has unexpected fields")
        state = value["state"]
        if type(state) is not str or state not in _STATES:
            raise ValueError("screen erase journal state is invalid")
        for key in ("active", "blocked", "completion_received"):
            if type(value[key]) is not bool:
                raise ValueError("screen erase journal flags are invalid")
        if (
            value["active"] != (state == "running")
            or value["blocked"] != (state in ("running", "uncertain"))
            or value["completion_received"] != (state == "completed")
        ):
            raise ValueError("screen erase journal state and flags are inconsistent")
        for key in ("operation_id", "target_session"):
            field = value[key]
            if state == "idle":
                if field is not None:
                    raise ValueError("idle screen erase journal has an operation identity")
            elif type(field) is not str or not 1 <= len(field) <= 256:
                raise ValueError("screen erase journal operation identity is invalid")
        error = value["error"]
        if state in ("uncertain", "acknowledged"):
            if type(error) is not str or not 1 <= len(error) <= 8192:
                raise ValueError("screen erase journal outcome error is invalid")
        elif error is not None:
            raise ValueError("screen erase journal has an unexpected error")
        elapsed = value["elapsed_seconds"]
        try:
            valid_elapsed = (
                type(elapsed) in (int, float) and elapsed >= 0 and math.isfinite(elapsed)
            )
        except OverflowError:
            valid_elapsed = False
        if not valid_elapsed:
            raise ValueError("screen erase journal elapsed time is invalid")
        return dict(value, elapsed_seconds=float(elapsed))

    def _load(self):
        try:
            with self.path.open("rb") as stream:
                raw = stream.read(MAX_JOURNAL_BYTES + 1)
        except FileNotFoundError:
            return
        if len(raw) > MAX_JOURNAL_BYTES:
            raise ValueError("screen erase journal exceeds 64 KiB")
        self._state = self._validate(json.loads(raw))
        if self._state["state"] == "running":
            self._state.update(
                state="uncertain",
                active=False,
                blocked=True,
                completion_received=False,
                error="screen erase was interrupted before the driver restarted",
            )
            self._persist(self._state)

    def _persist(self, value):
        profiles.save(self.path, value, overwrite=True)

    def _snapshot(self):
        result = dict(self._state)
        if result["state"] == "running" and self._started is not None:
            result["elapsed_seconds"] = max(0.0, self.clock() - self._started)
        return result

    def status(self):
        with self._lock:
            return self._snapshot()

    def start(self, keyboard, session):
        if type(session) is not str or not 1 <= len(session) <= 256:
            raise ValueError("screen erase target session is required")
        with self._lock:
            if self._state["blocked"] or self._state["active"]:
                raise ValueError("screen erase is already active or awaiting acknowledgement")
            operation_id = uuid.uuid4().hex
            record = {
                "operation_id": operation_id,
                "state": "running",
                "active": True,
                "blocked": True,
                "elapsed_seconds": 0.0,
                "completion_received": False,
                "error": None,
                "target_session": session,
            }
            self._persist(record)
            self._state = record
            self._started = self.clock()
            self._cancel = threading.Event()
            self._worker = threading.Thread(
                target=self._run, args=(keyboard, operation_id, self._cancel), daemon=True
            )
            try:
                self._worker.start()
            except Exception as error:
                self._finish(
                    operation_id, "uncertain", False, f"erase worker could not start: {error}"
                )
                raise
            return self._snapshot()

    def stop(self):
        with self._lock:
            worker, cancel = self._worker, self._cancel
            if worker is None or not worker.is_alive():
                return self._snapshot()
            cancel.set()
        if worker is not threading.current_thread():
            worker.join()
        return self.status()

    def acknowledge(self, operation_id):
        with self._lock:
            if (
                type(operation_id) is not str
                or operation_id != self._state["operation_id"]
                or self._state["state"] != "uncertain"
                or self._state["active"]
            ):
                raise ValueError(
                    "screen erase acknowledgement does not match an inactive uncertain operation"
                )
            record = dict(self._state, state="acknowledged", blocked=False)
            self._persist(record)
            self._state = record
            return self._snapshot()

    @staticmethod
    def _completion_received(result):
        return (
            isinstance(result, dict)
            and result.get("acknowledged") is True
            and result.get("completion_received") is True
        )

    def _run(self, keyboard, operation_id, cancel):
        try:
            result = keyboard.erase_screen(cancel=cancel, progress=self._progress)
            if self._completion_received(result):
                self._finish(operation_id, "completed", True, None)
            else:
                self._finish(
                    operation_id,
                    "uncertain",
                    False,
                    "screen erase returned without a completion confirmation",
                )
        except Exception as error:
            self._finish(operation_id, "uncertain", False, str(error) or type(error).__name__)

    def _progress(self, elapsed):
        with self._lock:
            if self._state["state"] == "running":
                self._state["elapsed_seconds"] = max(0.0, float(elapsed))

    def _finish(self, operation_id, state, completion_received, error):
        with self._lock:
            if self._state["operation_id"] != operation_id:
                return
            elapsed = self._snapshot()["elapsed_seconds"]
            record = dict(
                self._state,
                state=state,
                active=False,
                blocked=state == "uncertain",
                elapsed_seconds=elapsed,
                completion_received=completion_received,
                error=error[:4096] if error else None,
            )
            try:
                self._persist(record)
            except Exception as persist_error:
                record.update(
                    state="uncertain",
                    blocked=True,
                    completion_received=False,
                    error=f"could not persist screen erase result: {persist_error}"[:4096],
                )
                try:
                    self._persist(record)
                except Exception as retry_error:
                    # The on-disk running record remains conservative on restart.
                    record["error"] += (
                        f"; uncertain result also could not be persisted: {retry_error}"[:4096]
                    )
            self._state = record
            self._worker = None
            self._cancel = None
            self._started = None
