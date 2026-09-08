"""Knob slots derived from the exact model matrix and UI exclusions."""

import pytest
from test_h60 import _state
from test_he import Firmware, keyboard

from epomaker_driver import actions
from epomaker_driver.errors import ProtocolError
from epomaker_driver.he_knobs import knob_slots
from epomaker_driver.he_settings import plan_update
from epomaker_driver.models import data_file


def test_knob_slot_map_matches_default_media_actions_and_status():
    default = bytes(data_file("he60-matrices.json")["3417"]["defaultMatrix"])
    for name, slot in knob_slots(3417).items():
        assert default[slot * 4 : slot * 4 + 4] == actions.media(name)
    assert keyboard(Firmware(model_id=3417), product=0x5030).status()["knob_slots"] == knob_slots(
        3417
    )
    assert knob_slots(3365) == {}


@pytest.mark.parametrize("slot", [90, 91, 92])
def test_knob_excluded_from_magnetic_modes_switches_and_snap(slot):
    fw = Firmware(model_id=3417)
    kb = keyboard(fw, product=0x5030)
    with pytest.raises(ValueError, match="not magnetic"):
        plan_update(3417, slot, {"travel": 2}, _state(0x500))
    with pytest.raises(ValueError, match="not magnetic"):
        kb.set_magnetic_mode(
            slot, {"mode": "normal", "actions": ["00000400"], "travel": 2, "lift": 1, "deadzone": 0}
        )
    with pytest.raises(ValueError, match="not magnetic"):
        kb.set_switch_type([slot], "机械轴")
    with pytest.raises(ValueError, match="not magnetic"):
        kb.set_snap(slot, 1)
    assert not fw.sent


@pytest.mark.parametrize("playback", ["count", "toggle"])
def test_knob_accepts_nonheld_macros_and_ordinary_keys(playback):
    fw = Firmware(model_id=3417)
    kb = keyboard(fw, product=0x5030)
    for action in [actions.macro(4, playback), actions.keyboard("a"), bytes(4)]:
        assert kb.set_key(90, action) == list(action)
    assert kb.set_key(1, actions.macro(4, "held")) == list(actions.macro(4, "held"))


@pytest.mark.parametrize("hidden_index", [2, 3])
def test_two_timer_write_rejects_hidden_word_corruption(hidden_index):
    fw = Firmware(model_id=3417)
    original = fw.send

    def corrupt(command):
        original(command)
        if command[0] == 0x11:
            fw.sleep[hidden_index] ^= 1

    fw.send = corrupt
    kb = keyboard(fw, product=0x5030)
    with pytest.raises(ProtocolError, match="hidden sleep timers"):
        kb.set_sleep(0, 64800)
