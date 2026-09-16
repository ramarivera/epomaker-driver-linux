import pytest

from epomaker_driver.device import Keyboard
from epomaker_driver.errors import UnsupportedDevice


@pytest.mark.parametrize("transport", ["bluetooth", "24g", None, "unknown"])
def test_glyph_still_requires_usb_before_prepare_or_transfer(firmware, transport, monkeypatch):
    firmware.kind = transport
    keyboard = Keyboard(firmware)
    monkeypatch.setattr(
        "epomaker_driver.device.codec.screen_prepare",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("prepared")),
    )
    with pytest.raises(
        UnsupportedDevice, match="Glyph display uploads require a wired USB connection"
    ):
        keyboard.upload_screen(bytes(2), (0, 0, 1, 1))
    assert not firmware.sent


def test_glyph_still_usb_succeeds(firmware):
    firmware.kind = "usb"
    Keyboard(firmware).upload_screen(bytes(2), (0, 0, 1, 1))
    assert firmware.sent


def test_non_glyph_still_is_unchanged(firmware):
    firmware.model_id = 2895
    firmware.kind = None
    Keyboard(firmware).upload_screen(bytes(2), (0, 0, 1, 1))
    assert firmware.sent
