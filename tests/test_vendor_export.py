import copy

import pytest

from epomaker_driver import macros, snapshot
from epomaker_driver.device import Keyboard
from epomaker_driver.models import glyph_matrix
from epomaker_driver.vendor_config import preview
from epomaker_driver.vendor_export import export_record


def captured(firmware):
    return snapshot.capture(Keyboard(firmware))


def test_main_export_roundtrips_macro_payload_and_preserves_snapshot(firmware):
    firmware.matrices[0][36:40] = bytes([9, 0, 7, 0])
    firmware.macros[7] = bytearray(
        macros.encode(2, [{"hid_usage": 4, "down": True, "delay_ms": 10}])
    )
    source = captured(firmware)
    before = copy.deepcopy(source)
    record = export_record(source, name="Exported Glyph")
    assert record["name"] == "Exported Glyph"
    assert record["value"][0]["macroIndex"] == 7
    result = preview(record, include_macros=True)
    assert result["matrix"] == source["matrices"][0]
    assert result["macro_payloads"]["7"]["payload"] == source["macros"]["7"]
    assert source == before


def test_fn_custom_export_uses_normal_baseline(firmware):
    firmware.fn[0] = bytearray(glyph_matrix())
    firmware.fn[0][36:40] = bytes([0, 0, 99, 0])
    source = captured(firmware)
    record = export_record(source, "Fn Windows")
    assert record["fn"] is True
    assert record["value"][0]["original"] == 4
    assert preview(record, "Fn Windows")["matrix"] == source["fn"]["win"]


@pytest.mark.parametrize("target", ["Fn Windows", "Fn Mac"])
def test_factory_fn_defaults_reject_unresolvable_hidden_slots(firmware, target):
    with pytest.raises(ValueError, match="resolvable"):
        export_record(captured(firmware), target)


def test_invalid_macro_binding_and_name_are_rejected(firmware):
    firmware.matrices[0][36:40] = bytes([9, 3, 7, 0])
    source = captured(firmware)
    with pytest.raises(ValueError, match="invalid macro"):
        export_record(source)
    with pytest.raises(ValueError):
        export_record(source, name=" ")


def test_all_mouse_buttons_and_motion_roundtrip(firmware):
    events = [
        {"type": "mouse_button", "button": button, "down": False, "delay_ms": 128}
        for button in ("left", "right", "middle", "back", "forward")
    ] + [{"type": "mouse_move", "dx": -128, "dy": 127, "delay_ms": 15}]
    firmware.matrices[0][36:40] = bytes([9, 2, 3, 0])
    firmware.macros[3] = bytearray(macros.encode(65535, events))
    source = captured(firmware)
    record = export_record(source)
    action = record["value"][0]
    assert [event["value"] for event in action["macro"] if event["type"] == "mouse_button"] == [
        -1000,
        -999,
        -998,
        -996,
        -997,
    ]
    assert action["macroType"] == "touch_repeat"
    assert (
        preview(record, include_macros=True)["macro_payloads"]["3"]["payload"]
        == source["macros"]["3"]
    )


def test_duplicate_enter_occurrences_export_independently(firmware):
    firmware.matrices[0][81 * 4 : 82 * 4] = bytes([0, 1, 5, 0])
    firmware.matrices[0][103 * 4 : 104 * 4] = bytes([0, 2, 6, 0])
    source = captured(firmware)
    record = export_record(source)
    assert [(a["original"], a["index"]) for a in record["value"]] == [(40, 0), (40, 1)]
    assert preview(record)["matrix"] == source["matrices"][0]


@pytest.mark.parametrize(
    "options",
    [
        {"target": "other"},
        {"profile": True},
        {"profile": -1},
        {"profile": 3},
        {"target": "Fn Mac", "profile": 1},
        {"name": None},
        {"name": "x" * 101},
    ],
)
def test_invalid_export_selection(firmware, options):
    with pytest.raises(ValueError):
        export_record(captured(firmware), **options)


def test_reserved_macro_byte_and_ambiguous_payload_rejected(firmware):
    firmware.matrices[0][36:40] = bytes([9, 0, 7, 1])
    with pytest.raises(ValueError, match="invalid macro"):
        export_record(captured(firmware))
    firmware.matrices[0][39] = 0
    firmware.macros[7] = bytearray.fromhex("0100f9050102" + "00" * 250)
    from epomaker_driver.errors import ProtocolError

    with pytest.raises(ProtocolError, match="ambiguous"):
        export_record(captured(firmware))


def test_non_glyph_snapshot_rejected(firmware):
    firmware.model_id = 2895
    firmware.matrices.append(bytearray(512))
    with pytest.raises(ValueError, match="Glyph"):
        export_record(captured(firmware))
