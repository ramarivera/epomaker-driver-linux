import json
import threading
import time

import pytest

from epomaker_driver import profiles
from epomaker_driver.screen_erase_operation import ScreenEraseOperation


class Keyboard:
    def __init__(self, result=None):
        self.result = (
            {"acknowledged": True, "completion_received": True} if result is None else result
        )
        self.calls = 0
        self.entered = threading.Event()
        self.release = threading.Event()
        self.returned = threading.Event()

    def erase_screen(self, *, cancel, progress):
        self.calls += 1
        self.entered.set()
        progress(0.0)
        while not self.release.is_set():
            if cancel.is_set():
                raise RuntimeError("erase cancelled")
            time.sleep(0.001)
        self.returned.set()
        return self.result


def wait_for_return(keyboard):
    assert keyboard.returned.wait(1)


def test_success_and_acknowledged_completion(tmp_path):
    keyboard = Keyboard()
    operation = ScreenEraseOperation(tmp_path / "erase.json")
    started = operation.start(keyboard, "session-a")
    assert started["state"] == "running" and started["blocked"]
    assert keyboard.entered.wait(1)
    keyboard.release.set()
    wait_for_return(keyboard)
    operation.stop()
    assert operation.status()["completion_received"]
    assert operation.status()["blocked"] is False


def test_duplicate_start_invalid_session_and_active_ack_rejected(tmp_path):
    keyboard = Keyboard()
    operation = ScreenEraseOperation(tmp_path / "erase.json")
    with pytest.raises(ValueError):
        operation.start(keyboard, "")
    started = operation.start(keyboard, "session-a")
    with pytest.raises(ValueError):
        operation.start(keyboard, "session-b")
    with pytest.raises(ValueError):
        operation.acknowledge(started["operation_id"])
    keyboard.release.set()
    wait_for_return(keyboard)
    operation.stop()


def test_status_is_copy_and_unexpected_result_is_uncertain(tmp_path):
    keyboard = Keyboard(result=False)
    operation = ScreenEraseOperation(tmp_path / "erase.json")
    operation.start(keyboard, "session-a")
    keyboard.release.set()
    wait_for_return(keyboard)
    operation.stop()
    status = operation.status()
    assert status["state"] == "uncertain" and not status["completion_received"]
    status["state"] = "completed"
    assert operation.status()["state"] == "uncertain"
    with pytest.raises(ValueError):
        operation.start(Keyboard(), "session-b")


@pytest.mark.parametrize("result", [True, {}, {"completion_received": True}])
def test_completion_requires_explicit_acknowledged_result(tmp_path, result):
    keyboard = Keyboard(result=result)
    operation = ScreenEraseOperation(tmp_path / "erase.json")
    operation.start(keyboard, "session-a")
    keyboard.release.set()
    wait_for_return(keyboard)
    operation.stop()
    assert operation.status()["state"] == "uncertain"


def test_cancel_becomes_blocked_uncertain_and_ack_can_clear(tmp_path):
    keyboard = Keyboard()
    operation = ScreenEraseOperation(tmp_path / "erase.json")
    started = operation.start(keyboard, "session-a")
    assert keyboard.entered.wait(1)
    operation.stop()
    status = operation.status()
    assert status["state"] == "uncertain" and status["blocked"]
    acknowledged = operation.acknowledge(started["operation_id"])
    assert acknowledged["state"] == "acknowledged" and not acknowledged["blocked"]


def test_restart_running_journal_is_conservative(tmp_path):
    path = tmp_path / "erase.json"
    profiles.save(
        path,
        {
            "operation_id": "a" * 32,
            "state": "running",
            "active": True,
            "blocked": True,
            "elapsed_seconds": 1.0,
            "completion_received": False,
            "error": None,
            "target_session": "s",
        },
        overwrite=True,
    )
    operation = ScreenEraseOperation(path)
    assert operation.status()["state"] == "uncertain"


def test_terminal_restart_is_retained_without_resend(tmp_path):
    path = tmp_path / "erase.json"
    keyboard = Keyboard()
    operation = ScreenEraseOperation(path)
    operation.start(keyboard, "session-a")
    keyboard.release.set()
    wait_for_return(keyboard)
    operation.stop()
    first = operation.status()
    restarted = ScreenEraseOperation(path)
    assert restarted.status()["state"] == first["state"]
    assert keyboard.calls == 1


def test_acknowledged_restart_is_retained_without_resend(tmp_path):
    path = tmp_path / "erase.json"
    keyboard = Keyboard(result=False)
    operation = ScreenEraseOperation(path)
    started = operation.start(keyboard, "session-a")
    keyboard.release.set()
    wait_for_return(keyboard)
    operation.stop()
    operation.acknowledge(started["operation_id"])
    restarted = ScreenEraseOperation(path)
    assert restarted.status()["state"] == "acknowledged"
    assert keyboard.calls == 1


def test_acknowledgement_requires_exact_inactive_uncertain_id(tmp_path):
    keyboard = Keyboard(result=False)
    operation = ScreenEraseOperation(tmp_path / "erase.json")
    started = operation.start(keyboard, "session-a")
    keyboard.release.set()
    wait_for_return(keyboard)
    operation.stop()
    for candidate in (None, 1, "wrong", started["operation_id"][:-1]):
        with pytest.raises(ValueError):
            operation.acknowledge(candidate)


@pytest.mark.parametrize(
    "value",
    [
        {"state": "completed", "active": True},
        {"state": "uncertain", "blocked": False},
        {"state": "running", "active": False},
        {"state": "running", "operation_id": None},
        {"state": "completed", "operation_id": None},
        {"state": "unknown", "active": False},
    ],
)
def test_malformed_journal_types_and_consistency_fail_loud(tmp_path, value):
    path = tmp_path / "erase.json"
    base = {
        "operation_id": "a" * 32,
        "state": "uncertain",
        "active": False,
        "blocked": True,
        "elapsed_seconds": 1.0,
        "completion_received": False,
        "error": "x",
        "target_session": "s",
    }
    base.update(value)
    path.write_text(json.dumps(base))
    with pytest.raises(ValueError):
        ScreenEraseOperation(path)


def test_oversized_journal_fails_loud(tmp_path):
    path = tmp_path / "erase.json"
    path.write_text("{" + "x" * (64 * 1024) + "}")
    with pytest.raises(ValueError):
        ScreenEraseOperation(path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("operation_id", 1),
        ("active", "false"),
        ("blocked", 1),
        ("completion_received", None),
        ("elapsed_seconds", float("nan")),
        ("elapsed_seconds", float("inf")),
        ("elapsed_seconds", 10**1000),
        ("error", 3),
        ("target_session", []),
    ],
)
def test_journal_field_types_fail_loud(tmp_path, field, value):
    base = {
        "operation_id": "a" * 32,
        "state": "uncertain",
        "active": False,
        "blocked": True,
        "elapsed_seconds": 1.0,
        "completion_received": False,
        "error": "x",
        "target_session": "s",
    }
    base[field] = value
    path = tmp_path / "erase.json"
    path.write_text(json.dumps(base, allow_nan=True))
    with pytest.raises(ValueError):
        ScreenEraseOperation(path)


def test_start_persist_failure_does_not_touch_keyboard(tmp_path, monkeypatch):
    keyboard = Keyboard()

    def fail(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("epomaker_driver.screen_erase_operation.profiles.save", fail)
    operation = ScreenEraseOperation(tmp_path / "erase.json")
    with pytest.raises(OSError):
        operation.start(keyboard, "session-a")
    assert keyboard.calls == 0 and operation.status()["state"] == "idle"


def test_terminal_persist_failure_is_blocked_uncertain(tmp_path, monkeypatch):
    keyboard = Keyboard()
    path = tmp_path / "erase.json"
    original = profiles.save
    calls = 0

    def flaky(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("disk full")
        return original(*args, **kwargs)

    monkeypatch.setattr("epomaker_driver.screen_erase_operation.profiles.save", flaky)
    operation = ScreenEraseOperation(path)
    operation.start(keyboard, "session-a")
    keyboard.release.set()
    wait_for_return(keyboard)
    operation.stop()
    assert operation.status()["state"] == "uncertain"
    assert operation.status()["blocked"]


def test_repeated_terminal_persist_failure_leaves_running_journal_conservative(
    tmp_path, monkeypatch
):
    keyboard = Keyboard()
    path = tmp_path / "erase.json"
    original = profiles.save
    calls = 0

    def fail_terminal(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls >= 2:
            raise OSError("disk full")
        return original(*args, **kwargs)

    monkeypatch.setattr("epomaker_driver.screen_erase_operation.profiles.save", fail_terminal)
    operation = ScreenEraseOperation(path)
    operation.start(keyboard, "session-a")
    keyboard.release.set()
    wait_for_return(keyboard)
    operation.stop()
    monkeypatch.setattr("epomaker_driver.screen_erase_operation.profiles.save", original)
    restarted = ScreenEraseOperation(path)
    assert restarted.status()["state"] == "uncertain"
    assert restarted.status()["blocked"]


def test_elapsed_status_uses_injected_clock(tmp_path):
    now = [10.0]

    def clock():
        return now[0]

    keyboard = Keyboard()
    operation = ScreenEraseOperation(tmp_path / "erase.json", clock=clock)
    operation.start(keyboard, "session-a")
    now[0] = 12.5
    assert operation.status()["elapsed_seconds"] == 2.5
    keyboard.release.set()
    wait_for_return(keyboard)
    operation.stop()


def test_ack_persist_failure_keeps_uncertain_blocked(tmp_path, monkeypatch):
    keyboard = Keyboard(result=False)
    path = tmp_path / "erase.json"
    operation = ScreenEraseOperation(path)
    operation.start(keyboard, "session-a")
    keyboard.release.set()
    operation.stop()
    original = profiles.save
    monkeypatch.setattr(
        "epomaker_driver.screen_erase_operation.profiles.save",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(OSError):
        operation.acknowledge(operation.status()["operation_id"])
    assert operation.status()["state"] == "uncertain"
    assert operation.status()["blocked"]
    monkeypatch.setattr("epomaker_driver.screen_erase_operation.profiles.save", original)


def test_thread_start_failure_becomes_uncertain(tmp_path, monkeypatch):
    keyboard = Keyboard()

    def fail_start(_):
        raise RuntimeError("thread unavailable")

    monkeypatch.setattr(threading.Thread, "start", fail_start)
    operation = ScreenEraseOperation(tmp_path / "erase.json")
    with pytest.raises(RuntimeError):
        operation.start(keyboard, "session-a")
    assert operation.status()["state"] == "uncertain"
    assert operation.status()["blocked"]
    # A persisted running journal is conservative on the next process start.
    restarted = ScreenEraseOperation(tmp_path / "erase.json")
    assert restarted.status()["state"] == "uncertain"
    assert restarted.status()["blocked"]
    assert keyboard.calls == 0


def test_malformed_journal_fails_loud(tmp_path):
    path = tmp_path / "erase.json"
    path.write_text(json.dumps({"state": "running"}))
    with pytest.raises(ValueError):
        ScreenEraseOperation(path)


def test_idle_journal_roundtrip_has_no_pending_operation(tmp_path):
    path = tmp_path / "erase.json"
    original = ScreenEraseOperation(path)
    profiles.save(path, original.status())
    restarted = ScreenEraseOperation(path)
    assert restarted.status() == original.status()
    assert not restarted.status()["blocked"]


@pytest.mark.parametrize(
    "change",
    [
        {"operation_id": "orphaned-operation"},
        {"target_session": "orphaned-session"},
        {"error": "unexplained failure"},
    ],
)
def test_idle_journal_rejects_residual_operation_data(tmp_path, change):
    path = tmp_path / "erase.json"
    state = ScreenEraseOperation(path).status()
    profiles.save(path, dict(state, **change))
    with pytest.raises(ValueError):
        ScreenEraseOperation(path)
