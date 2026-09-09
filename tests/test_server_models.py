from types import SimpleNamespace

import pytest

from epomaker_driver.backend_factory import verify_device_identity
from epomaker_driver.errors import UnsupportedDevice
from epomaker_driver.gui_contract import ui_descriptor


def _info(vendor=0x3151, product=0x5004):
    return SimpleNamespace(vendor_id=vendor, product_id=product)


def _identity(device_id):
    return {"device_id": device_id, "is_boot": False}


def test_identity_verification_accepts_glyph_transport_alias():
    assert verify_device_identity(_info(), _identity(3059))["id"] == 3059


def test_identity_verification_rejects_mismatched_product():
    with pytest.raises(UnsupportedDevice, match="does not match"):
        verify_device_identity(_info(product=0x9999), _identity(3059))


def test_ui_descriptor_common_keyboard_contract():
    ui = ui_descriptor(3059)
    assert ui["macro_slots"] == 256
    assert ui["picture_banks"] == 5
    assert ui["picture_slots"] == 126
    assert "side_lighting" in ui["controls"]


def test_ui_descriptor_he3417_exposes_public_sleep_fields_only():
    ui = ui_descriptor(3417)
    assert ui["sleep_fields"] == ["bt", "dongle"]
    assert set(ui["sleep_limits"]) == {"bt", "dongle"}
