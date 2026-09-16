import pytest

from epomaker_driver.device import Keyboard
from epomaker_driver.errors import UnsupportedDevice

KNOBS = (53, 108, 109)


@pytest.mark.parametrize("slot", KNOBS)
@pytest.mark.parametrize("os_mode", (0, 1))
def test_glyph_knobs_reject_fn_assignments_before_write(firmware, slot, os_mode):
    keyboard = Keyboard(firmware)

    with pytest.raises(UnsupportedDevice, match="Fn"):
        keyboard.set_key(slot, [0, 0, 4, 0], fn=True, os_mode=os_mode)

    assert firmware.sent == []


@pytest.mark.parametrize("slot", KNOBS)
@pytest.mark.parametrize("container", (list, bytes, bytearray, memoryview))
def test_glyph_knobs_reject_held_macro_before_write(firmware, slot, container):
    keyboard = Keyboard(firmware)

    with pytest.raises(UnsupportedDevice, match="held"):
        keyboard.set_key(slot, container(bytes([9, 2, 7, 0])))

    assert firmware.sent == []


@pytest.mark.parametrize("slot", KNOBS)
@pytest.mark.parametrize("action", ([0, 0, 4, 0], [0, 0, 0, 0], [9, 0, 7, 0], [9, 1, 7, 0]))
def test_glyph_knobs_accept_keys_and_nonheld_macros(firmware, slot, action):
    keyboard = Keyboard(firmware)

    result = keyboard.set_key(slot, action)

    assert result == action
    assert len(firmware.sent) == 1


def test_glyph_nonknob_and_normal_fn_remain_usable(firmware):
    keyboard = Keyboard(firmware)

    assert keyboard.set_key(52, [9, 2, 7, 0]) == [9, 2, 7, 0]
    assert keyboard.set_key(52, [0, 0, 4, 0], fn=True) == [0, 0, 4, 0]


def test_non_glyph_knobs_are_unchanged(firmware):
    firmware.model_id = 2895
    keyboard = Keyboard(firmware)

    assert keyboard.set_key(53, [9, 2, 7, 0]) == [9, 2, 7, 0]
