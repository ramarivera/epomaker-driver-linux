import json
import uuid

import pytest

from epomaker_driver import config_library

MATRIX = "00" * 512


def test_crud_restart_and_revision_conflicts(tmp_path):
    library = config_library.ConfigLibrary(tmp_path / "library")
    assert library.list() == []
    entry = library.save("  Alpha ", MATRIX, "Main")
    assert entry == library.get(entry["id"], 1)
    assert entry["name"] == "Alpha"
    assert entry["model_id"] == 3059
    assert entry["revision"] == 1
    assert (tmp_path / "library" / f"{entry['id']}.json").stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="conflict"):
        library.save("Stale", MATRIX, "Fn Mac", entry["id"], 2)
    updated = library.save("Beta", "a5" * 512, "Fn Windows", entry["id"], 1)
    assert config_library.ConfigLibrary(tmp_path / "library").list() == [updated]
    with pytest.raises(ValueError, match="conflict"):
        library.get(entry["id"], 1)
    assert library.delete(entry["id"], 2) == {"ok": True}


@pytest.mark.parametrize("matrix", ["0" * 1023, "0" * 1025, "00" * 511 + "0g", "00" * 511 + " 0"])
def test_matrix_is_exact_canonical_hex(tmp_path, matrix):
    with pytest.raises(ValueError, match="matrix"):
        config_library.ConfigLibrary(tmp_path).save("x", matrix, "Main")


def test_matrix_uppercase_is_normalized_to_canonical_lowercase(tmp_path):
    entry = config_library.ConfigLibrary(tmp_path).save("x", "A5" * 512, "Main")
    assert entry["matrix"] == "a5" * 512


@pytest.mark.parametrize("name", [None, 1, True, "", " ", "x" * 21])
def test_name_is_strict_and_bounded(tmp_path, name):
    with pytest.raises(ValueError, match="name"):
        config_library.ConfigLibrary(tmp_path).save(name, MATRIX, "Main")


@pytest.mark.parametrize("layer", ["main", "Fn", "Fn Linux", ""])
def test_layer_is_strict(tmp_path, layer):
    with pytest.raises(ValueError, match="layer"):
        config_library.ConfigLibrary(tmp_path).save("x", MATRIX, layer)


def test_bounds_and_corrupt_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(config_library, "MAX_ENTRIES", 1)
    library = config_library.ConfigLibrary(tmp_path / "library")
    first = library.save("First", MATRIX, "Main")
    with pytest.raises(ValueError, match="too many"):
        library.save("Second", MATRIX, "Main")
    monkeypatch.setattr(config_library, "MAX_ENTRIES", 4096)
    bad = tmp_path / "library" / ("f" * 32 + ".json")
    bad.write_text("not json")
    with pytest.raises(ValueError, match="invalid config library entry"):
        library.list()
    bad.unlink()
    huge = tmp_path / "library" / ("e" * 32 + ".json")
    huge.write_bytes(b"{" + b"x" * config_library.MAX_ENTRY_BYTES)
    with pytest.raises(ValueError, match="exceeds size limit"):
        library.list()
    assert first["revision"] == 1


def test_shape_and_filename_corruption(tmp_path):
    path = tmp_path / "library"
    entry = config_library.ConfigLibrary(path).save("Good", MATRIX, "Main")
    wrong = path / ("1" * 32 + ".json")
    wrong.write_text(json.dumps(entry))
    with pytest.raises(ValueError, match="filename id"):
        config_library.ConfigLibrary(path).list()


def test_uuid_collision_does_not_clobber(tmp_path, monkeypatch):
    ident = "4" * 32
    monkeypatch.setattr(config_library.uuid, "uuid4", lambda: uuid.UUID(hex=ident))
    library = config_library.ConfigLibrary(tmp_path)
    first = library.save("First", MATRIX, "Main")
    with pytest.raises(ValueError, match="already exists"):
        library.save("Second", MATRIX, "Main")
    assert library.list() == [first]


def test_get_and_delete_require_existing_revision(tmp_path):
    library = config_library.ConfigLibrary(tmp_path)
    with pytest.raises(ValueError, match="does not exist"):
        library.get("0" * 32, 1)
    entry = library.save("x", MATRIX, "Main")
    with pytest.raises(ValueError, match="conflict"):
        library.delete(entry["id"], 2)


@pytest.mark.parametrize("ident", [None, "../escape", "A" * 32])
def test_ids_are_rejected_before_filesystem_access(tmp_path, ident):
    with pytest.raises(ValueError, match="id"):
        config_library.ConfigLibrary(tmp_path).get(ident, 1)


@pytest.mark.parametrize("revision", [None, 0, False, "1"])
def test_revisions_are_positive_strict_integers(tmp_path, revision):
    with pytest.raises(ValueError, match="revision"):
        config_library.ConfigLibrary(tmp_path).get("0" * 32, revision)


def test_save_revision_requires_id_and_missing_update_is_rejected(tmp_path):
    library = config_library.ConfigLibrary(tmp_path)
    with pytest.raises(ValueError, match="requires"):
        library.save("x", MATRIX, "Main", revision=1)
    with pytest.raises(ValueError, match="does not exist"):
        library.save("x", MATRIX, "Main", "0" * 32, 1)


def test_missing_delete_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        config_library.ConfigLibrary(tmp_path).delete("0" * 32, 1)


def test_malformed_model_schema_and_filename_are_actionable(tmp_path):
    path = tmp_path / "library"
    path.mkdir()
    valid_id = "0" * 32
    base = {
        "id": valid_id,
        "revision": 1,
        "name": "x",
        "model_id": config_library.MODEL_ID,
        "matrix": MATRIX,
        "layer": "Main",
    }
    (path / f"{valid_id}.json").write_text(json.dumps({**base, "model_id": 99}))
    with pytest.raises(ValueError, match="model"):
        config_library.ConfigLibrary(path).list()
    (path / f"{valid_id}.json").write_text(json.dumps({"id": valid_id}))
    with pytest.raises(ValueError, match="unexpected fields"):
        config_library.ConfigLibrary(path).list()
    (path / f"{valid_id}.json").unlink()
    (path / "not-an-id.json").write_text(json.dumps(base))
    with pytest.raises(ValueError, match="filename must"):
        config_library.ConfigLibrary(path).list()


def test_list_rejects_overfull_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(config_library, "MAX_ENTRIES", 1)
    path = tmp_path / "library"
    path.mkdir()
    for ident in ("0" * 32, "1" * 32):
        (path / f"{ident}.json").write_text("{}")
    with pytest.raises(ValueError, match="too many"):
        config_library.ConfigLibrary(path).list()
