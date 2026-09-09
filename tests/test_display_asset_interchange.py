import base64
import io

import pytest
from PIL import Image

from epomaker_driver.display_library import PORTABLE_SCHEMA, DisplayLibrary
from epomaker_driver.server import Controller


def asset_bytes(animated=False):
    output = io.BytesIO()
    image = Image.new("RGB", (2, 2), "red")
    if animated:
        image.save(
            output,
            format="GIF",
            save_all=True,
            append_images=[Image.new("RGB", (2, 2), "blue")],
            duration=0,
        )
    else:
        image.save(output, format="PNG")
    return output.getvalue()


def portable(name="asset", kind="screen", delay=None, raw=None):
    return {
        "schema": PORTABLE_SCHEMA,
        "version": 1,
        "model_id": 3059,
        "name": name,
        "kind": kind,
        "delay_ms": delay,
        "content": base64.b64encode(
            asset_bytes(kind == "animation") if raw is None else raw
        ).decode(),
    }


def test_export_import_roundtrip_preserves_source_and_uses_new_ids(tmp_path):
    library = DisplayLibrary(tmp_path / "assets")
    for kind in ("screen", "animation"):
        source = asset_bytes(kind == "animation")
        saved = library.save(kind, kind, None, base64.b64encode(source).decode())
        exported = library.export(saved["id"])
        assert set(exported) == {
            "schema",
            "version",
            "model_id",
            "name",
            "kind",
            "delay_ms",
            "content",
        }
        assert base64.b64decode(exported["content"]) == source
        assert exported["delay_ms"] == (0 if kind == "animation" else None)
        imported = library.import_asset(exported)
        repeated = library.import_asset(exported)
        assert imported["id"] != saved["id"]
        assert repeated["id"] not in {saved["id"], imported["id"]}
        assert library.get(imported["id"])["content"] == exported["content"]


@pytest.mark.parametrize(
    "field,value", [("schema", "wrong"), ("version", True), ("model_id", True)]
)
def test_import_rejects_malformed_contract_without_writing(tmp_path, field, value):
    candidate = portable()
    candidate[field] = value
    with pytest.raises((ValueError, OSError)):
        DisplayLibrary(tmp_path / "assets").import_asset(candidate)
    assert DisplayLibrary(tmp_path / "assets").list() == []


@pytest.mark.parametrize(
    "kind,delay,raw",
    [
        ("screen", 1, None),
        ("animation", None, asset_bytes(True)),
        ("other", None, None),
        ("screen", None, b"bad"),
    ],
)
def test_import_rejects_kind_delay_or_content_without_writing(tmp_path, kind, delay, raw):
    value = portable(kind=kind, delay=delay, raw=raw)
    with pytest.raises((ValueError, OSError)):
        DisplayLibrary(tmp_path / "assets").import_asset(value)
    assert DisplayLibrary(tmp_path / "assets").list() == []


def test_import_rejects_unknown_fields_and_api_is_offline(tmp_path):
    library = DisplayLibrary(tmp_path / "assets")
    saved = library.import_asset(portable())
    bad = library.export(saved["id"])
    bad["extra"] = True
    with pytest.raises(ValueError, match="unexpected fields"):
        library.import_asset(bad)
    controller = Controller(
        tmp_path / "backups",
        assets_dir=tmp_path / "api-assets",
        discovery=lambda: (_ for _ in ()).throw(AssertionError()),
    )
    imported = controller.call("display_asset_import", {"value": library.export(saved["id"])})
    assert imported["name"] == "asset"


@pytest.mark.parametrize(
    "candidate",
    [
        None,
        [],
        {},
        {**portable(), "content": "!"},
        {**portable(kind="animation", delay=0), "delay_ms": True},
    ],
)
def test_invalid_portable_values_do_not_create_library(tmp_path, candidate):
    path = tmp_path / "assets"
    with pytest.raises(ValueError):
        DisplayLibrary(path).import_asset(candidate)
    assert not path.exists()
