import datetime

import pytest
from test_he import Firmware, keyboard

from epomaker_driver import codec
from epomaker_driver.device import display_spec as device_display_spec
from epomaker_driver.errors import ProtocolError, UnsupportedDevice
from epomaker_driver.models import display_spec


class DisplayFirmware(Firmware):
    accept_after = 1

    def exchange(self, command):
        if command[0] == 0xA5:
            self.query_log.append(bytes(command))
            accepted = sum(item[0] == 0xA5 for item in self.query_log) >= self.accept_after
            return bytes([command[0], int(accepted)]) + bytes(62)
        return super().exchange(command)


@pytest.fixture
def display_keyboard():
    firmware = DisplayFirmware(model_id=2376)
    return keyboard(firmware, product=0x502F), firmware


def test_he65_display_uses_rgb565_prepare_and_chunks(display_keyboard):
    kb, firmware = display_keyboard
    kb.identify()
    pixels = (bytes(range(256)) * (128 * 128 * 2 // 256 + 1))[: 128 * 128 * 2]
    kb.upload_screen(pixels, (0, 0, 128, 128), frame=4)

    prepare = next(command for command in firmware.query_log if command[0] == 0xA5)
    assert prepare[1:4] == bytes((4, 1, 0))
    assert prepare[4:6] == len(pixels).to_bytes(2, "little")
    chunks = [command for command in firmware.sent if command[0] == 0x25]
    assert len(chunks) == 586
    assert [int.from_bytes(c[4:6], "little") for c in chunks] == list(range(586))
    assert chunks[-1][6] == 8
    assert prepare[6] == 0 and prepare[16:18] == bytes(2)
    assert all(command[1] == 4 and command[2] == 1 for command in chunks)
    assert b"".join(command[8:] for command in chunks)[: len(pixels)] == pixels
    assert not any(command[0] in (0xA9, 0x29) for command in firmware.sent)


def test_he65_animation_bounds_and_packet_metadata(display_keyboard):
    kb, firmware = display_keyboard
    kb.identify()
    frame = bytes(128 * 128 * 2)
    kb.upload_animation([frame, frame], 80)
    prepare = next(command for command in firmware.query_log if command[0] == 0xA5)
    assert prepare[1:4] == bytes((0, 2, 80))

    before = len(firmware.sent)
    with pytest.raises(ValueError, match="2..165"):
        kb.upload_animation([frame] * 166, 80)
    assert len(firmware.sent) == before


def test_he65_clock_language_and_status_display():
    firmware = DisplayFirmware(model_id=2376)
    kb = keyboard(firmware, product=0x502F)
    kb.identify()
    kb.sync_clock(datetime.datetime(2026, 9, 9, 12, 34, 56))
    kb.toggle_display_language()
    assert [command[0] for command in firmware.sent[-2:]] == [0x28, 0x27]
    assert firmware.sent[-2][8:15] == bytes.fromhex("07ea09090c2238")
    assert firmware.sent[-1][1] == 1
    status = kb.status()
    assert status["display"] == {
        "width": 128,
        "height": 128,
        "banks": 5,
        "max_frames": 165,
        "pixel_bytes": 2,
    }
    assert "display" in status["capabilities"]


@pytest.mark.parametrize("model_id", [3727, 3759, 2520])
def test_display_opcodes_are_rejected_for_other_he_models(model_id):
    firmware = DisplayFirmware(model_id=model_id)
    product = 0x502C if model_id == 3727 else 0x502E if model_id == 3759 else 0x502F
    kb = keyboard(firmware, product=product)
    kb.identify()
    before = len(firmware.sent)
    with pytest.raises(UnsupportedDevice, match="display"):
        kb._check_commands([codec.packet([0xA5])])
    assert len(firmware.sent) == before


def test_he65_display_spec_is_rgb565():
    assert display_spec(2376)["pixel_bytes"] == 2
    assert device_display_spec(2376)["width"] == 128


def test_he65_prepare_retries_and_fails_before_chunks(display_keyboard):
    kb, firmware = display_keyboard
    firmware.accept_after = 12
    kb.identify()
    with pytest.raises(ProtocolError, match="not accepted"):
        kb.upload_screen(bytes(128 * 128 * 2), (0, 0, 128, 128))
    assert len([command for command in firmware.sent if command[0] == 0x25]) == 0
    assert len([command for command in firmware.query_log if command[0] == 0xA5]) == 11


@pytest.mark.parametrize("opcode", [0x29, 0xA9, 0x22])
def test_unsupported_display_variants_never_send(display_keyboard, opcode):
    kb, firmware = display_keyboard
    with pytest.raises(UnsupportedDevice):
        kb._write([codec.packet([opcode])])
    assert not firmware.sent


def test_prepare_becomes_ready_before_chunks(display_keyboard):
    kb, firmware = display_keyboard
    firmware.accept_after = 3
    kb.upload_screen(bytes([0x12, 0x34]), (0, 0, 1, 1))
    assert len([q for q in firmware.query_log if q[0] == 0xA5]) == 3
    assert len(firmware.sent) == 1
    assert firmware.sent[0][8:10] == bytes([0x12, 0x34])


def test_display_cli_image_clock_language(monkeypatch, tmp_path, capsys):
    from PIL import Image
    from test_he_recovery_cli import install

    from epomaker_driver import cli

    _, firmware, info = install(monkeypatch, 2376)
    original = firmware.exchange

    def exchange(command):
        if command[0] == 0xA5:
            firmware.query_log.append(bytes(command))
            return bytes([0xA5, 1]) + bytes(62)
        return original(command)

    firmware.exchange = exchange
    still = tmp_path / "still.png"
    Image.new("RGB", (128, 128), (255, 0, 0)).save(still)
    for command in [["screen", str(still), "--bank", "5"], ["clock"], ["display-language-toggle"]]:
        assert cli.main(["--device", info.path] + command) == 0
        capsys.readouterr()
    chunks = [p for p in firmware.sent if p[0] == 0x25]
    assert len(chunks) == 586 and chunks[0][1] == 4
    assert chunks[0][8:10] == bytes.fromhex("f800")
    assert [p[0] for p in firmware.sent[-2:]] == [0x28, 0x27]
