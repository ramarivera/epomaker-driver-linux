import pytest

from epomaker_driver.device import Keyboard
from epomaker_driver.discovery import DeviceInfo
from epomaker_driver.errors import UnsupportedDevice
from epomaker_driver.server import Controller


def test_glyph_firmware_versions_queries_identity_and_components(firmware):
    firmware.usb_version = 0x0500
    seen = []
    original = firmware.exchange

    def exchange(command, **options):
        seen.append(command[0])
        return original(command, **options)

    firmware.exchange = exchange
    assert Keyboard(firmware).read_firmware_versions() == {
        "usb": 0x0500,
        "rf": 0x1234,
        "mled": 0x0401,
        "oled": 0x0302,
        "flash": 0xABCD,
    }
    assert seen == [0x8F, 0x80, 0xAE, 0xAD]
    assert not firmware.sent


def test_malformed_component_reply_fails_without_partial_result(firmware):
    original = firmware.exchange

    def exchange(command, **options):
        if command[0] == 0xAE:
            return bytes([0xAE, 1])
        return original(command, **options)

    firmware.exchange = exchange
    with pytest.raises(ValueError, match="mled version response"):
        Keyboard(firmware).read_firmware_versions()
    assert not firmware.sent


def test_bootloader_and_non_glyph_are_rejected(firmware):
    original = firmware.exchange

    def boot_exchange(command, **options):
        response = original(command, **options)
        if command[0] == 0x8F:
            response = bytearray(response)
            response[9] = 1
            return bytes(response)
        return response

    firmware.exchange = boot_exchange
    with pytest.raises(UnsupportedDevice):
        Keyboard(firmware).read_firmware_versions()
    firmware.model_id = 2895
    firmware.exchange = original
    with pytest.raises(UnsupportedDevice, match="Glyph only"):
        Keyboard(firmware).read_firmware_versions()


def test_server_firmware_version_read_is_explicit_and_read_only(firmware, descriptor, tmp_path):
    info = DeviceInfo(
        "/dev/hidraw-test",
        "Glyph simulator",
        3,
        0x3151,
        0x5002,
        descriptor,
        "usb",
        0,
    )
    controller = Controller(
        tmp_path / "backups",
        discovery=lambda: [info],
        transport_factory=lambda _: firmware,
    )
    try:
        controller.call("connect", {"path": info.path})
        value = controller.call("read", {"section": "firmware_versions"})
        assert value["flash"] == 0xABCD
        assert not firmware.sent
    finally:
        controller.close()


def test_all_version_queries_share_transaction_and_refresh_identity(firmware):
    keyboard = Keyboard(firmware)
    keyboard.identify()
    firmware.usb_version = 0x1234
    active = False
    original = firmware.exchange

    def transaction(operation):
        nonlocal active
        active = True
        try:
            return operation()
        finally:
            active = False

    def exchange(command, **options):
        assert active
        if command[0] in (0x80, 0xAE, 0xAD):
            return bytes([command[0]]) + bytes(63)
        return original(command, **options)

    firmware.transaction = transaction
    firmware.exchange = exchange
    assert keyboard.read_firmware_versions() == {
        "usb": 0x1234,
        "rf": None,
        "mled": None,
        "oled": None,
        "flash": None,
    }
    assert keyboard.identity["usb_version"] == 0x1234
    assert not firmware.sent
