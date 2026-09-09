import pytest

from epomaker_driver.device import Keyboard
from epomaker_driver.errors import UnsupportedDevice
from epomaker_driver.live_lighting import frame_packets


def glyph_keyboard(firmware):
    firmware.identity = {
        "device_id": 3059,
        "usb_version": 1,
        "is_boot": False,
        "light_sync": True,
    }
    firmware.model_id = 3059
    keyboard = Keyboard(firmware)
    keyboard.identity = firmware.identity
    keyboard.model = {"displayName": "Epomaker Glyph", "layer": 3}
    return keyboard


def test_live_frame_packets_have_vendor_headers_checksum_and_padding():
    colors = bytes(range(256)) + bytes(range(122))
    packets = frame_packets(colors)

    assert len(packets) == 7
    assert all(len(packet) == 64 for packet in packets)
    assert packets[0][:8] == bytes.fromhex("0f 01 00 38 00 00 00 b7")
    assert packets[0][8:] == colors[:56]
    assert packets[-1][:8] == bytes.fromhex("0f 01 06 38 01 00 00 b0")
    assert packets[-1][8:50] == colors[-42:]
    assert packets[-1][50:] == bytes(14)


@pytest.mark.parametrize("value", [b"", bytes(377), bytes(379), [0] * 378, None])
def test_live_frame_validation_happens_before_encoding(value):
    with pytest.raises((TypeError, ValueError)):
        frame_packets(value)


def test_send_live_colors_validates_full_frame_before_writes(firmware):
    keyboard = glyph_keyboard(firmware)
    with pytest.raises(ValueError, match="exactly 378"):
        keyboard.send_live_colors(bytes(377))
    assert firmware.sent == []


def test_send_live_colors_writes_one_complete_frame(firmware):
    keyboard = glyph_keyboard(firmware)
    assert keyboard.send_live_colors(bytes(range(256)) + bytes(range(122))) == 7
    assert firmware.sent == list(frame_packets(bytes(range(256)) + bytes(range(122))))


@pytest.mark.parametrize(
    "mutator, message",
    [
        (lambda fw: setattr(fw, "kind", "bluetooth"), "wired USB"),
        (lambda fw: setattr(fw, "kind", None), "wired USB"),
        (lambda fw: fw.identity.update(light_sync=False), "support"),
        (lambda fw: fw.identity.update(is_boot=True), "bootloader"),
        (lambda fw: fw.identity.update(device_id=2895), "Glyph"),
    ],
)
def test_send_live_colors_rejects_unsupported_runtime(mutator, message, firmware):
    keyboard = glyph_keyboard(firmware)
    mutator(firmware)
    with pytest.raises(UnsupportedDevice, match=message):
        keyboard.send_live_colors(bytes(378))
    assert firmware.sent == []


def test_send_live_colors_stops_on_transport_error_without_extra_packets(firmware):
    keyboard = glyph_keyboard(firmware)
    original_send = firmware.send

    def fail_on_second(command, **options):
        if len(firmware.sent) == 1:
            raise RuntimeError("transport failed")
        original_send(command, **options)

    firmware.send = fail_on_second
    with pytest.raises(RuntimeError, match="transport failed"):
        keyboard.send_live_colors(bytes(378))
    assert len(firmware.sent) == 1
