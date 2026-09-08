"""Exercise the HE lighting mixin through real USB packet wrapping."""

import pytest

from epomaker_driver import codec
from epomaker_driver.device import Keyboard
from epomaker_driver.errors import ProtocolError, UnsupportedDevice
from epomaker_driver.he_lighting import HELightingMixin
from epomaker_driver.transport import Transport


@pytest.fixture(params=[3727, 3759])
def lights(request):
    class USB:
        response = bytes(64)
        light = bytearray(codec.light("solid"))
        pictures = [bytearray(384) for _ in range(5)]
        sent = []
        drop_write = False

        def set_feature(self, report):
            assert len(report) == 65 and report[0] == 0
            command = report[1:]
            self.sent.append(command)
            if command[0] == 0x87:
                self.response = bytes([0x87]) + bytes(self.light[1:])
            elif command[0] == 7:
                assert (sum(command[:9]) & 255) == 255
                if not self.drop_write:
                    self.light = bytearray(command)
            elif command[0] == 0x8C:
                self.response = bytes(
                    self.pictures[command[1]][command[3] * 64 : (command[3] + 1) * 64]
                )
            elif command[0] == 0x0C:
                if not self.drop_write:
                    start, count = command[3] * 56, command[4]
                    self.pictures[command[1]][start : start + count] = command[8 : 8 + count]
            else:
                pytest.fail(f"unexpected command {command[0]:x}")

        def get_feature(self, report_id, length):
            assert (report_id, length) == (0, 64)
            return self.response

        def close(self):
            pass

    class Backend(HELightingMixin, Keyboard):
        expected_id = request.param

        def _supported(self):
            pass  # Product/identity gates are exercised in tests/test_he.py.

        def _check_commands(self, commands):
            assert all(c[0] in (7, 0x87, 0x0C, 0x8C) for c in commands)

    usb = USB()
    return Backend(Transport(usb, "usb", sleep=lambda _: None)), usb


@pytest.mark.parametrize("mode", [m for m in codec.LIGHT_MODES if m != "off"])
def test_he_all_catalog_lighting_modes_roundtrip(lights, mode):
    kb, usb = lights
    value = kb.set_light(mode)
    assert value["mode"] == mode and value["brightness"] == 4
    assert usb.sent[0][0] == 7 and usb.sent[0][2] == 4


def test_he_lighting_exact_wire_and_readback_failure(lights):
    kb, usb = lights
    value = kb.set_light("wave", rgb=0x123456, brightness=2, speed=4, option=3, rainbow=True)
    assert value["rainbow"] and value["speed"] == 4
    assert usb.sent[0] == bytes.fromhex("07040002381234561e") + bytes(55)
    usb.drop_write = True
    with pytest.raises(ProtocolError, match="readback differs"):
        kb.set_light("breathing", rgb=0x987654)


@pytest.mark.parametrize(
    "mode,options",
    [
        ("off", {}),
        ("wave", {"side": True}),
        ("unknown", {}),
        ("wave", {"option": 4}),
        ("snake", {"option": 2}),
        ("solid", {"speed": 1}),
        ("music", {"option": 3}),
        ("neon", {"rainbow": True}),
        ("picture", {"rgb": 0x123456}),
        ("wave", {"rainbow": 1}),
        ("wave", {"speed": 5}),
    ],
)
def test_he_lighting_rejects_unexposed_controls_before_reports(lights, mode, options):
    kb, usb = lights
    with pytest.raises((ValueError, UnsupportedDevice)):
        kb.set_light(mode, **options)
    assert not usb.sent


def test_he_picture_bank_limits_and_reserved_suffix(lights):
    kb, usb = lights
    bank = 2 if kb.expected_id == 3727 else 4
    usb.pictures[bank][378:] = b"\xaa" * 6
    colors = bytes((i * 7) & 255 for i in range(378))
    kb.write_picture(colors, bank)
    assert kb.read_picture(bank) == colors
    assert usb.pictures[bank][378:] == b"\xaa" * 6
    kb.set_light("picture", option=bank)
    assert usb.light[4] == bank << 4
    before = len(usb.sent)
    for action in (
        lambda: kb.read_picture(bank + 1),
        lambda: kb.write_picture(colors, bank + 1),
        lambda: kb.set_light("picture", option=bank + 1),
        lambda: kb.get_light(side=True),
    ):
        with pytest.raises((ValueError, UnsupportedDevice)):
            action()
    assert len(usb.sent) == before
