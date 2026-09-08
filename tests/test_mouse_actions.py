import pytest

from epomaker_driver import mouse_actions

EXPECTED = {
    "left": "0100f000",
    "right": "0100f100",
    "middle": "0100f200",
    "back": "0100f300",
    "forward": "0100f400",
    "wheel-left": "0100f500",
    "wheel-right": "0100f600",
    "wheel-up": "0100f700",
    "wheel-down": "0100f800",
    "scroll-up": "0100f501",
    "scroll-down": "0100f5ff",
    "move-left": "0100f6fb",
    "move-right": "0100f605",
    "move-up": "0100f7fb",
    "move-down": "0100f705",
    "dpi-cycle": "14000000",
    "dpi-up": "14000100",
    "dpi-down": "00020014",
    "profile-cycle": "08000300",
    "pairing": "0a050000",
    "lighting-cycle": "0d010000",
}


def test_every_ch585_binding_has_exact_vendor_bytes():
    assert set(mouse_actions.BINDINGS) == set(EXPECTED)
    for name, expected in EXPECTED.items():
        assert mouse_actions.mouse(name) == bytes.fromhex(expected)
        assert mouse_actions.BINDINGS[name] == bytes.fromhex(expected)


def test_decode_prefers_semantic_mouse_names_and_preserves_raw():
    for name, expected in EXPECTED.items():
        assert mouse_actions.decode(bytes.fromhex(expected)) == {
            "type": "mouse",
            "name": name,
            "raw": expected,
        }


@pytest.mark.parametrize("raw", [bytes.fromhex("11010203"), bytes.fromhex("0300ffff")])
def test_unknown_actions_preserve_raw(raw):
    assert mouse_actions.decode(raw) == {"type": "unknown", "raw": raw.hex()}


def test_zero_action_is_disabled():
    assert mouse_actions.decode(bytes(4)) == {"type": "disabled", "raw": "00000000"}


@pytest.mark.parametrize("raw", [bytes.fromhex(value) for value in ("00000100", "00000300")])
def test_reserved_keyboard_looking_mouse_values_remain_unknown(raw):
    assert mouse_actions.decode(raw) == {"type": "unknown", "raw": raw.hex()}


@pytest.mark.parametrize(
    "call", [lambda: mouse_actions.mouse("invalid"), lambda: mouse_actions.mouse(None)]
)
def test_unknown_mouse_binding_is_strict(call):
    with pytest.raises(ValueError, match="unknown mouse action"):
        call()


@pytest.mark.parametrize("raw", [b"", bytes(3), bytes(5), 4, True, "00000000", [0, 0, 0, 0]])
def test_decode_rejects_non_four_byte_actions(raw):
    with pytest.raises(ValueError, match="four bytes"):
        mouse_actions.decode(raw)
