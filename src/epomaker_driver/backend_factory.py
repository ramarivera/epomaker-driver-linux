"""Model-aware keyboard backend construction for the GUI server."""

from __future__ import annotations

from .device import Keyboard
from .errors import UnsupportedDevice
from .he import HE_PRODUCTS, HEKeyboard
from .legacy import LegacyKeyboard
from .models import model_by_id


def backend_for_transport(transport, *, product_id: int):
    """Construct a read/write keyboard backend from the USB product family."""
    if product_id in HE_PRODUCTS:
        return HEKeyboard(transport, product_id=product_id)
    if product_id == 0x4015:
        return LegacyKeyboard(transport)
    return Keyboard(transport)


def reject_non_keyboard(identity):
    """Reject mouse identities before exposing a GUI connection."""
    model = model_by_id(identity["device_id"])
    if model.get("type") != "keyboard":
        raise UnsupportedDevice("the graphical interface supports keyboards only")
    return model


def verify_device_identity(info, identity):
    model = reject_non_keyboard(identity)
    vid = int(model.get("vidHex", "0"), 16)
    pid = int(model.get("pidHex", "0"), 16)
    # Glyph command transports use product 0x5004 while the catalog identity is 0x5002.
    valid_products = {(vid, pid)}
    if identity["device_id"] == 3059:
        valid_products.add((0x3151, 0x5004))
    if (info.vendor_id, info.product_id) not in valid_products:
        raise UnsupportedDevice("identified model does not match the selected USB product")
    return model
