import pytest

from epomaker_driver import actions
from epomaker_driver.models import glyph_matrix


def test_binding_packets_and_catalog():
    assert actions.keyboard("c", modifiers=["ctrl", "shift"]) == bytes.fromhex("00030600")
    assert actions.keyboard("a", second="b") == bytes.fromhex("00000405")
    assert actions.keyboard(4, modifiers=["ctrl", "ctrl"]) == bytes.fromhex("00010400")
    for key, usage in actions.KEYS.items():
        assert actions.keyboard(key)[2] == usage
    for name, usage in actions.MEDIA.items():
        data = actions.media(name)
        assert data[2:] == usage.to_bytes(2, "little")
        assert actions.decode(data)["name"] == name
    for name in actions.MOUSE:
        assert actions.decode(actions.mouse(name))["name"] == name
    for mode in actions.MACRO_MODES:
        assert actions.decode(actions.macro(255, mode)) == {
            "type": "macro",
            "slot": 255,
            "mode": mode,
            "raw": actions.macro(255, mode).hex(),
        }
    matrix = glyph_matrix()
    for slot, name in ((53, "play-pause"), (108, "volume-up"), (109, "volume-down")):
        assert actions.media(name) == matrix[slot * 4 : slot * 4 + 4]


def test_decoding_preserves_original_actions():
    for raw in (bytes(4), bytes([0, 0, 3, 0])):
        assert actions.decode(raw) == {"type": "disabled", "raw": raw.hex()}
    for raw in (
        bytes([0, 0, 1, 0]),
        bytes([17, 1, 2, 3]),
        bytes([3, 0, 255, 255]),
        bytes([9, 3, 0, 0]),
        bytes([9, 0, 0, 1]),
        bytes([1, 1, 240, 0]),
    ):
        assert actions.decode(raw) == {"type": "unknown", "raw": raw.hex()}
    assert actions.decode(actions.keyboard("c", modifiers=["ctrl"]))["modifiers"] == ["ctrl"]


@pytest.mark.parametrize(
    "call",
    [
        lambda: actions.keyboard("invalid"),
        lambda: actions.keyboard(True),
        lambda: actions.keyboard("a", modifiers=["invalid"]),
        lambda: actions.media("invalid"),
        lambda: actions.mouse("invalid"),
        lambda: actions.macro(0, "invalid"),
        lambda: actions.macro(256),
        lambda: actions.decode(b"x"),
    ],
)
def test_invalid_binding(call):
    with pytest.raises(ValueError):
        call()
