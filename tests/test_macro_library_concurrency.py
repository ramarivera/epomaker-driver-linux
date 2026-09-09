"""Independent library instances must not lose concurrent edits."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from epomaker_driver.macro_library import MacroLibrary


def test_two_instances_cannot_replace_the_same_revision(tmp_path):
    first, second = MacroLibrary(tmp_path), MacroLibrary(tmp_path)
    value = {"repeat": 1, "events": []}
    initial = first.save("Original", value, "count")
    ready = Barrier(2)

    def update(store, name):
        ready.wait(timeout=5)
        try:
            return store.save(name, value, "held", initial["id"], initial["revision"])
        except ValueError as error:
            assert "revision conflict" in str(error)
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(update, first, "First")
        two = pool.submit(update, second, "Second")
        results = [one.result(timeout=10), two.result(timeout=10)]
    winners = [entry for entry in results if entry is not None]
    assert len(winners) == 1
    assert winners[0]["revision"] == 2
    assert MacroLibrary(tmp_path).list() == winners


def test_delete_cannot_remove_a_newer_revision(tmp_path):
    first, second = MacroLibrary(tmp_path), MacroLibrary(tmp_path)
    value = {"repeat": 1, "events": []}
    original = first.save("Original", value, "count")
    updated = second.save("Updated", value, "toggle", original["id"], 1)
    try:
        first.delete(original["id"], 1)
    except ValueError as error:
        assert "revision conflict" in str(error)
    else:
        raise AssertionError("stale deletion removed a newer library entry")
    assert first.list() == [updated]
