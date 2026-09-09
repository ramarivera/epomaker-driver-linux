import base64
import io

import pytest
from PIL import Image

from epomaker_driver.device import Keyboard
from epomaker_driver.discovery import DeviceInfo
from epomaker_driver.errors import UnsupportedDevice
from epomaker_driver.server import Controller


def animation_content():
    output = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(
        output,
        format="GIF",
        save_all=True,
        append_images=[Image.new("RGB", (2, 2), "blue")],
        duration=80,
    )
    return base64.b64encode(output.getvalue()).decode()


def test_glyph_bluetooth_animation_is_rejected_before_transfer(firmware):
    firmware.kind = "bluetooth"
    keyboard = Keyboard(firmware)
    frame = bytes(428 * 142 * 2)
    with pytest.raises(UnsupportedDevice, match="wired USB"):
        keyboard.upload_animation([frame, frame], 80)
    assert not firmware.sent


def test_glyph_unknown_transport_is_rejected_before_transfer(firmware):
    firmware.kind = None
    keyboard = Keyboard(firmware)
    frame = bytes(428 * 142 * 2)
    with pytest.raises(UnsupportedDevice, match="wired USB"):
        keyboard.upload_animation([frame, frame], 80)
    assert not firmware.sent


def test_glyph_missing_transport_attribute_is_rejected(firmware):
    del firmware.kind
    keyboard = Keyboard(firmware)
    frame = bytes(428 * 142 * 2)
    with pytest.raises(UnsupportedDevice, match="wired USB"):
        keyboard.upload_animation([frame, frame], 80)
    assert not firmware.sent


def test_glyph_multiframe_screen_path_has_the_same_gate(firmware):
    firmware.kind = "bluetooth"
    keyboard = Keyboard(firmware)
    frame = bytes(428 * 142 * 2)
    with pytest.raises(UnsupportedDevice, match="wired USB"):
        keyboard.upload_screen(frame, (0, 0, 428, 142), frames=2)
    assert not firmware.sent


def test_glyph_usb_animation_succeeds(firmware):
    firmware.kind = "usb"
    keyboard = Keyboard(firmware)
    frame = bytes(428 * 142 * 2)
    keyboard.upload_animation([frame, frame], 80)
    assert firmware.sent


def test_glyph_still_upload_is_unchanged_on_bluetooth(firmware):
    firmware.kind = "bluetooth"
    keyboard = Keyboard(firmware)
    keyboard.upload_screen(bytes(2), (0, 0, 1, 1))
    assert firmware.sent


def test_non_glyph_animation_is_not_subject_to_glyph_transport_gate(firmware):
    firmware.model_id = 2895
    firmware.kind = None
    keyboard = Keyboard(firmware)
    frame = bytes(320 * 172 * 2)
    keyboard.upload_animation([frame, frame], 80)
    assert firmware.sent


def test_controller_exposes_actual_transport_and_rejects_bluetooth_animation(
    firmware, descriptor, tmp_path
):
    firmware.kind = "bluetooth"
    info = DeviceInfo(
        "/dev/hidraw-test",
        "Glyph simulator",
        5,
        0x3151,
        0x5004,
        descriptor,
        "bluetooth",
        6,
    )
    controller = Controller(
        tmp_path / "backups",
        discovery=lambda: [info],
        transport_factory=lambda _: firmware,
    )
    try:
        identity = controller.call("connect", {"path": info.path})
        assert identity["transport"] == "bluetooth"
        with pytest.raises(UnsupportedDevice, match="wired USB"):
            controller.call("write", {"kind": "animation", "content": animation_content()})
        assert not firmware.sent
    finally:
        controller.close()
