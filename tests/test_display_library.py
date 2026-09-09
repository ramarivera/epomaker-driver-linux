import base64
import io
import json
import multiprocessing
import os

import pytest
from PIL import Image

from epomaker_driver import display_library
from epomaker_driver.display_library import DisplayLibrary
from epomaker_driver.server import Controller


def content(animated=False):
    output = io.BytesIO()
    image = Image.new("RGB", (2, 2), "red")
    if animated:
        image.save(
            output,
            format="GIF",
            save_all=True,
            append_images=[Image.new("RGB", (2, 2), "blue")],
            duration=80,
        )
    else:
        image.save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode()


def test_display_library_crud_restart_and_preview(tmp_path):
    library = DisplayLibrary(tmp_path / "assets")
    entry = library.save("  startup  ", "screen", None, content())
    assert entry["name"] == "startup"
    assert entry["frame_count"] == 1
    assert list(library.list()) == [entry]
    full = library.get(entry["id"])
    assert full["content"] == content()
    assert full["preview_png"]
    restarted = DisplayLibrary(tmp_path / "assets")
    assert restarted.list() == [entry]
    assert restarted.delete(entry["id"]) == {"ok": True}
    assert restarted.list() == []


def test_animation_stores_effective_delay_and_list_omits_content(tmp_path):
    entry = DisplayLibrary(tmp_path / "assets").save("anim", "animation", None, content(True))
    assert entry["delay_ms"] == 80
    assert set(entry) == {"id", "name", "kind", "delay_ms", "frame_count", "pixel_bytes"}


@pytest.mark.parametrize(
    "name,kind,delay,value,message",
    [
        (" ", "screen", None, content(), "blank"),
        ("x" * 81, "screen", None, content(), "80"),
        ("x", "other", None, content(), "kind"),
        ("x", "screen", 1, content(), "still"),
        ("x", "screen", None, "%%%", "canonical"),
    ],
)
def test_display_library_rejects_invalid_assets(tmp_path, name, kind, delay, value, message):
    with pytest.raises(ValueError, match=message):
        DisplayLibrary(tmp_path / "assets").save(name, kind, delay, value)


@pytest.mark.parametrize("name", [None, 3])
def test_display_library_rejects_non_text_names(tmp_path, name):
    with pytest.raises(ValueError, match="name must be text"):
        DisplayLibrary(tmp_path / "assets").save(name, "screen", None, content())


def test_corrupt_record_fails_explicitly_and_bad_id_is_rejected(tmp_path):
    directory = tmp_path / "assets"
    directory.mkdir()
    (directory / "not-an-id.json").write_text("{}")
    with pytest.raises(ValueError, match="filename"):
        DisplayLibrary(directory).list()
    with pytest.raises(ValueError, match="32 lowercase"):
        DisplayLibrary(directory).get("../escape")


def test_corrupt_persisted_schema_and_content_fail_explicitly(tmp_path):
    library = DisplayLibrary(tmp_path / "assets")
    saved = library.save("asset", "screen", None, content())
    path = library.directory / f"{saved['id']}.json"
    record = json.loads(path.read_text())
    record["content"] = "%%%%"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="canonical"):
        library.list()
    record = json.loads(path.read_text())
    record["content"] = saved.get("content", content())
    record["extra"] = True
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="unexpected fields"):
        library.list()


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("version", True, "model or version"),
        ("model_id", True, "model or version"),
        ("frame_count", 2, "frame_count"),
        ("pixel_bytes", 1, "pixel_bytes"),
    ],
)
def test_persisted_metadata_is_strictly_validated(tmp_path, field, value, message):
    library = DisplayLibrary(tmp_path / "assets")
    saved = library.save("asset", "screen", None, content())
    path = library.directory / f"{saved['id']}.json"
    record = json.loads(path.read_text())
    record[field] = value
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match=message):
        library.list()


def test_get_detects_metadata_mismatch_after_list_validation(tmp_path):
    library = DisplayLibrary(tmp_path / "assets")
    saved = library.save("asset", "screen", None, content())
    path = library.directory / f"{saved['id']}.json"
    record = json.loads(path.read_text())
    record["pixel_bytes"] += 121552
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="pixel_bytes"):
        library.get(saved["id"])


def test_duplicate_id_and_capacity_do_not_clobber(tmp_path, monkeypatch):
    library = DisplayLibrary(tmp_path / "assets")
    ident = "a" * 32
    monkeypatch.setattr(display_library.uuid, "uuid4", lambda: type("UUID", (), {"hex": ident})())
    first = library.save("first", "screen", None, content())
    with pytest.raises(ValueError, match="already exists"):
        library.save("second", "screen", None, content())
    assert library.get(first["id"])["name"] == "first"
    monkeypatch.setattr(display_library, "MAX_ENTRIES", 1)
    with pytest.raises(ValueError, match="too many"):
        library.save("third", "screen", None, content())


def test_oversized_record_is_bounded(tmp_path):
    directory = tmp_path / "assets"
    directory.mkdir()
    (directory / ("b" * 32 + ".json")).write_bytes(b"x" * (display_library.MAX_ENTRY_BYTES + 1))
    with pytest.raises(ValueError, match="exceeds size"):
        DisplayLibrary(directory).list()


def test_base64_decoded_limit_and_private_permissions(tmp_path):
    library = DisplayLibrary(tmp_path / "assets")
    entry = library.save("asset", "screen", None, content())
    assert os.stat(library.directory).st_mode & 0o777 == 0o700
    assert os.stat(library.directory / f"{entry['id']}.json").st_mode & 0o777 == 0o600
    oversized = base64.b64encode(b"x" * (display_library.MAX_DECODED_BYTES + 1)).decode()
    with pytest.raises(ValueError, match="14 MiB"):
        library.save("large", "screen", None, oversized)


def test_missing_delete_is_explicit(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        DisplayLibrary(tmp_path / "assets").delete("a" * 32)


def _save_from_process(directory, name):
    DisplayLibrary(directory).save(name, "screen", None, content())


def test_independent_process_saves_preserve_both_entries(tmp_path):
    context = multiprocessing.get_context("fork")
    directory = tmp_path / "assets"
    processes = [
        context.Process(target=_save_from_process, args=(directory, f"asset-{i}")) for i in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join()
        assert process.exitcode == 0
    assert {entry["name"] for entry in DisplayLibrary(directory).list()} == {"asset-0", "asset-1"}


def test_controller_display_library_is_offline(tmp_path):
    controller = Controller(
        tmp_path / "backups",
        assets_dir=tmp_path / "assets",
        discovery=lambda: (_ for _ in ()).throw(AssertionError()),
    )
    saved = controller.call(
        "display_asset_save",
        {"name": "asset", "kind": "screen", "delay_ms": None, "content": content()},
    )
    assert controller.call("display_library", {})["entries"] == [saved]
    full = controller.call("display_asset_get", {"id": saved["id"]})
    assert full["preview_png"]
    assert controller.call("display_asset_delete", {"id": saved["id"]}) == {"ok": True}
