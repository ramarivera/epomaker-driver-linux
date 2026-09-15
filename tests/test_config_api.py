import copy

import pytest

from epomaker_driver.device import Keyboard
from epomaker_driver.errors import DeviceUnavailable, UnsupportedDevice
from epomaker_driver.models import glyph_matrix
from epomaker_driver.server import Controller


def saved(controller, layer="Main"):
    matrix = bytearray(glyph_matrix())
    matrix[:4] = bytes([0, 1, 5, 0])
    return controller.call(
        "config_library_save",
        {
            "name": "Work",
            "matrix": matrix.hex(),
            "layer": layer,
        },
    )


def test_offline_crud_and_revision(tmp_path):
    controller = Controller(tmp_path)
    assert controller.call("config_library", {}) == {"entries": []}
    entry = saved(controller)
    assert controller.call("config_library", {}) == {"entries": [entry]}
    renamed = controller.call("config_library_save", {**entry, "name": "Travel"})
    assert renamed["revision"] == 2
    assert renamed["matrix"] == entry["matrix"]
    with pytest.raises(ValueError, match="conflict"):
        controller.call("config_library_delete", entry)
    with pytest.raises(DeviceUnavailable):
        controller.call("write", {"kind": "config", **renamed})
    controller.call("config_library_delete", renamed)
    assert controller.call("config_library", {}) == {"entries": []}


@pytest.mark.parametrize(
    "layer,profile", [("Main", 0), ("Main", 2), ("Fn Windows", 0), ("Fn Mac", 0)]
)
def test_apply_only_saved_target(tmp_path, firmware, layer, profile):
    controller = Controller(tmp_path)
    controller.keyboard = Keyboard(firmware)
    before_matrices = copy.deepcopy(firmware.matrices)
    before_fn = copy.deepcopy(firmware.fn)
    entry = saved(controller, layer)
    controller.call(
        "write", {"kind": "config", "id": entry["id"], "revision": 1, "profile": profile}
    )
    expected = bytes.fromhex(entry["matrix"])
    if layer == "Main":
        before_matrices[profile] = expected
    else:
        before_fn[int(layer == "Fn Mac")] = expected
    assert firmware.matrices == before_matrices
    assert firmware.fn == before_fn
    assert not firmware.macros


@pytest.mark.parametrize("profile", [-1, 3, True, "1"])
def test_invalid_profile_no_writes(tmp_path, firmware, profile):
    controller = Controller(tmp_path)
    controller.keyboard = Keyboard(firmware)
    entry = saved(controller)
    with pytest.raises(ValueError):
        controller.call("write", {"kind": "config", **entry, "profile": profile})
    assert not firmware.sent


def test_conflicts_fn_target_and_identity_prevent_writes(tmp_path, firmware):
    controller = Controller(tmp_path)
    controller.keyboard = Keyboard(firmware)
    entry = saved(controller, "Fn Mac")
    for extra, message in [({"revision": 2}, "conflict"), ({"profile": 1}, "profile 0")]:
        with pytest.raises(ValueError, match=message):
            controller.call("write", {"kind": "config", **entry, **extra})
    firmware.model_id = 9999
    with pytest.raises(UnsupportedDevice):
        controller.call("write", {"kind": "config", **entry})
    assert not firmware.sent


def test_config_readback_mismatch_is_reported(tmp_path, firmware, monkeypatch):
    from epomaker_driver.errors import ProtocolError

    controller = Controller(tmp_path)
    controller.keyboard = Keyboard(firmware)
    entry = saved(controller)
    monkeypatch.setattr(firmware, "send", lambda *args, **kwargs: None)
    with pytest.raises(ProtocolError, match="readback differs"):
        controller.call("write", {"kind": "config", **entry})


def test_other_model_is_rejected(tmp_path, firmware, monkeypatch):
    controller = Controller(tmp_path)
    controller.keyboard = Keyboard(firmware)
    entry = saved(controller)
    monkeypatch.setattr(controller.keyboard, "identify", lambda: {"device_id": 3060})
    with pytest.raises(UnsupportedDevice, match="Glyph only"):
        controller.call("write", {"kind": "config", **entry})
    assert not firmware.sent
