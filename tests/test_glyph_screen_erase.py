import pytest

from epomaker_driver.device import Keyboard
from epomaker_driver.errors import ProtocolError, ResponseTimeout, UnsupportedDevice


def test_glyph_screen_erase_sends_one_checked_packet(firmware):
    sent = []
    original = firmware.exchange

    def exchange(command, **options):
        sent.append(command)
        if command[0] == 0xAC:
            return bytes.fromhex("acaaaa5555") + bytes(59)
        return original(command, **options)

    firmware.exchange = exchange
    response = Keyboard(firmware).request_screen_erase()
    assert response[:5] == bytes.fromhex("acaaaa5555")
    erase = [command for command in sent if command[0] == 0xAC]
    assert erase == [bytes.fromhex("ac00000000000053") + bytes(56)]


@pytest.mark.parametrize(
    "response", [b"short", bytes(64), bytes.fromhex("acaaaa555400") + bytes(58)]
)
def test_invalid_ack_is_protocol_error_without_retry(firmware, response):
    calls = []
    original = firmware.exchange

    def exchange(command, **options):
        if command[0] == 0xAC:
            calls.append(command)
            return response
        return original(command, **options)

    firmware.exchange = exchange
    with pytest.raises(ProtocolError):
        Keyboard(firmware).request_screen_erase()
    assert len(calls) == 1


def test_timeout_propagates_without_retry(firmware):
    calls = []
    original = firmware.exchange

    def exchange(command, **options):
        if command[0] == 0xAC:
            calls.append(command)
            raise ResponseTimeout("no erase ACK")
        return original(command, **options)

    firmware.exchange = exchange
    with pytest.raises(ResponseTimeout):
        Keyboard(firmware).request_screen_erase()
    assert len(calls) == 1


@pytest.mark.parametrize("model,boot", [(2895, False), (3059, True)])
def test_wrong_model_or_boot_rejects_before_erase(firmware, model, boot):
    firmware.model_id = model
    calls = []
    original = firmware.exchange

    def exchange(command, **options):
        if command[0] == 0xAC:
            calls.append(command)
        return original(command, **options)

    firmware.exchange = exchange
    keyboard = Keyboard(firmware)
    if boot:
        original_identify = keyboard.identify

        def identify():
            result = original_identify()
            keyboard.identity["is_boot"] = True
            return result

        keyboard.identify = identify
    with pytest.raises(UnsupportedDevice):
        keyboard.request_screen_erase()
    assert not calls


@pytest.mark.parametrize("transport", ["usb", "bluetooth"])
def test_erase_is_not_transport_gated(firmware, transport):
    firmware.kind = transport
    original = firmware.exchange
    firmware.exchange = lambda command, **options: (
        bytes.fromhex("acaaaa5555") + bytes(59)
        if command[0] == 0xAC
        else original(command, **options)
    )
    Keyboard(firmware).request_screen_erase()
