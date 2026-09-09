import json
import uuid

import pytest

from epomaker_driver import macro_library

VALUE = {"repeat": 1, "events": [{"hid_usage": 4, "down": True, "delay_ms": 10}]}


@pytest.mark.parametrize(
    "operation, value, message",
    [
        (
            "save",
            {"name": "x", "value": VALUE, "mode": "count", "ident": "../escape", "revision": 1},
            "id",
        ),
        (
            "save",
            {"name": "x", "value": VALUE, "mode": "count", "ident": "A" * 32, "revision": 1},
            "id",
        ),
        (
            "save",
            {"name": "x", "value": VALUE, "mode": "count", "ident": "0" * 32, "revision": True},
            "revision",
        ),
        (
            "save",
            {"name": "x", "value": VALUE, "mode": "count", "ident": "0" * 32, "revision": 0},
            "revision",
        ),
        ("delete", {"ident": "../escape", "revision": 1}, "id"),
        ("delete", {"ident": "0" * 32, "revision": False}, "revision"),
    ],
)
def test_ids_and_revisions_are_strict(tmp_path, operation, value, message):
    library = macro_library.MacroLibrary(tmp_path / "library")
    with pytest.raises(ValueError, match=message):
        if operation == "save":
            library.save(**value)
        else:
            library.delete(value["ident"], value["revision"])


@pytest.mark.parametrize("name", [None, 1, True])
def test_name_must_be_text(tmp_path, name):
    with pytest.raises(ValueError, match="name"):
        macro_library.MacroLibrary(tmp_path / "library").save(name, VALUE, "count")


def test_mixed_events_roundtrip_and_input_mutation_isolated(tmp_path):
    value = {
        "repeat": 3,
        "events": [
            {"type": "keyboard", "hid_usage": 4, "down": True, "delay_ms": 10},
            {"type": "mouse_button", "button": "back", "down": False, "delay_ms": 128},
            {"type": "mouse_move", "dx": -3, "dy": 7, "delay_ms": 10},
        ],
    }
    library = macro_library.MacroLibrary(tmp_path / "library")
    entry = library.save("Mixed", value, "held")
    value["events"][0]["hid_usage"] = 99
    value["events"].append({"hid_usage": 5, "down": False, "delay_ms": 10})
    assert library.list() == [entry]
    assert entry["value"]["events"][0] == {"hid_usage": 4, "down": True, "delay_ms": 10}


def test_stored_filename_and_shape_corruption_is_actionable(tmp_path):
    path = tmp_path / "library"
    library = macro_library.MacroLibrary(path)
    entry = library.save("Good", VALUE, "count")
    wrong_name = path / ("1" * 32 + ".json")
    wrong_name.write_text(json.dumps(entry))
    with pytest.raises(ValueError, match="filename id"):
        library.list()

    wrong_name.unlink()
    (path / "not-an-id.json").write_text(json.dumps(entry))
    with pytest.raises(ValueError, match="filename must"):
        library.list()

    (path / "not-an-id.json").unlink()
    (path / f"{'2' * 32}.json").write_text(json.dumps({"id": "2" * 32}))
    with pytest.raises(ValueError, match="unexpected fields"):
        library.list()


def test_oversize_entry_is_bounded(tmp_path):
    path = tmp_path / "library"
    path.mkdir()
    (path / f"{'3' * 32}.json").write_bytes(b"{" + b"x" * macro_library.MAX_ENTRY_BYTES)
    with pytest.raises(ValueError, match="exceeds size limit"):
        macro_library.MacroLibrary(path).list()


def test_capacity_preserves_existing_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(macro_library, "MAX_ENTRIES", 1)
    library = macro_library.MacroLibrary(tmp_path / "library")
    first = library.save("First", VALUE, "count")
    with pytest.raises(ValueError, match="too many"):
        library.save("Second", VALUE, "count")
    assert library.list() == [first]


def test_uuid_collision_is_no_clobber(tmp_path, monkeypatch):
    ident = "4" * 32
    monkeypatch.setattr(macro_library.uuid, "uuid4", lambda: uuid.UUID(hex=ident))
    library = macro_library.MacroLibrary(tmp_path / "library")
    first = library.save("First", VALUE, "count")
    with pytest.raises(ValueError, match="already exists"):
        library.save("Second", VALUE, "toggle")
    assert library.list() == [first]


def test_update_missing_entry_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        macro_library.MacroLibrary(tmp_path / "library").save(
            "Missing", VALUE, "count", "5" * 32, 1
        )
