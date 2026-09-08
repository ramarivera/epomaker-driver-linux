import pytest

from epomaker_driver import codec, macros
from epomaker_driver.errors import ProtocolError


def test_mixed_macro_matches_recovered_layout():
    events = [
        {"hid_usage": 4, "down": True, "delay_ms": 127},
        {"type": "mouse_button", "button": "back", "down": False, "delay_ms": 128},
        {"type": "mouse_move", "dx": -128, "dy": 127, "delay_ms": 10},
    ]
    data = macros.encode(5, events)
    assert data[:14] == bytes.fromhex("050004fff3008000f900807f0a00")
    assert macros.decode(data) == {"repeat": 5, "events": events}
    assert macros.encode(**macros.decode(data)) == data


@pytest.mark.parametrize("delay", [1, 127, 128, 65535])
def test_all_button_events(delay):
    events = [
        {"type": "mouse_button", "button": button, "down": down, "delay_ms": delay}
        for button in macros.BUTTONS
        for down in (False, True)
    ]
    assert macros.decode(macros.encode(65535, events)) == {"repeat": 65535, "events": events}


def test_exact_capacity_and_keyboard_compatibility():
    events = [{"hid_usage": 239, "down": False, "delay_ms": 1}] * 127
    data = macros.encode(1, events)
    assert data == codec.macro_data(1, events)
    assert len(macros.decode(data)["events"]) == 127
    typed = [{"type": "keyboard", **events[0]}]
    assert macros.encode(1, typed) == macros.encode(1, events[:1])
    assert macros.decode(bytes(256)) == {"repeat": 0, "events": []}


@pytest.mark.parametrize(
    "events",
    [
        None,
        [None],
        [{}],
        [{"type": "invalid"}],
        [{"type": "mouse_button", "button": [], "down": True, "delay_ms": 1}],
        [{"type": "mouse_move"}],
        [{"type": "mouse_move", "dx": -129, "dy": 0, "delay_ms": 1}],
        [{"type": "mouse_move", "dx": 0, "dy": 0, "delay_ms": 0}],
        [{"hid_usage": 4, "down": True, "delay_ms": 1}] * 128,
    ],
)
def test_bad_events(events):
    with pytest.raises(ValueError):
        macros.encode(1, events)


@pytest.mark.parametrize(
    "data, message",
    [
        (b"", "exactly"),
        (bytes(2) + bytes.fromhex("f9010000") + bytes(250), "compact"),
        (bytes(2) + bytes.fromhex("ff01") + bytes(252), "unsupported"),
        (bytes(2) + bytes.fromhex("04800000") + bytes(250), "zero-delay"),
        (bytes(2) + bytes.fromhex("f90000000000") + bytes(248), "zero-delay"),
        (bytes(2) + bytes([4, 1]) * 126 + bytes([249, 0]), "truncated mouse"),
        (bytes(2) + bytes([4, 1]) * 126 + bytes([4, 0]), "truncated macro delay"),
    ],
)
def test_invalid_or_ambiguous_storage(data, message):
    with pytest.raises(ProtocolError, match=message):
        macros.decode(data)
