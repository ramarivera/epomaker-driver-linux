import json

from epomaker_driver import codec, server


def test_catalog_exposes_glyph_lighting_metadata_without_removing_flat_maps(tmp_path):
    catalog = server.Controller(tmp_path).call("catalog", {})
    assert catalog["light_modes"] == codec.LIGHT_MODES
    assert catalog["side_modes"] == codec.SIDE_MODES
    capabilities = catalog["lighting_capabilities"]
    assert capabilities["main"]["types"][0]["type"] == "LightWave"
    assert len(capabilities["main"]["types"]) == 22
    assert len(capabilities["side"]["types"]) == 6


def test_glyph_capability_source_contains_effect_options_and_limits():
    with open("src/epomaker_driver/data/glyph-lighting-capabilities.json") as handle:
        capabilities = json.load(handle)
    wave = next(item for item in capabilities["main"]["types"] if item["type"] == "LightWave")
    assert wave["maxValue"] == 4 and wave["maxSpeed"] == 4
    assert wave["options"] == ["向右", "向左", "向下", "向上"]
    music = next(
        item for item in capabilities["main"]["types"] if item["type"] == "LightMusicFollow2"
    )
    assert music["options"] == ["upright", "separate", "intersect"]
    assert codec.LIGHT_MODES["music"] == 22
    assert codec.LIGHT_MODES["screen"] == 21
