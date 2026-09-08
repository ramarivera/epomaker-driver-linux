import json

import pytest
from test_he import Firmware, keyboard

from epomaker_driver import cli
from epomaker_driver.discovery import DeviceInfo
from epomaker_driver.errors import ProtocolError


def _make_advanced(fw, profile, first=9, second=21):
    modes = bytearray(fw.fields[7])
    modes[first] = 0x82
    modes[second] = 0x83
    fw.fields[7] = bytes(modes)
    for mode in range(4):
        for slot, marker in ((first, 0x40 + mode), (second, 0x50 + mode)):
            data = bytearray(fw.matrices[(profile, mode)])
            data[slot * 4 : slot * 4 + 4] = bytes((marker, marker, marker, marker))
            fw.matrices[(profile, mode)] = bytes(data)


@pytest.mark.parametrize("product,model", [(0x502C, 3727), (0x502E, 3759)])
@pytest.mark.parametrize("profile", [0, 1])
def test_snap_pair_usb_packets_and_advanced_cleanup(product, model, profile):
    fw = Firmware(model_id=model)
    _make_advanced(fw, profile)
    kb = keyboard(fw, product=product)
    kb.identify()
    if profile:
        kb.set_profile(profile)
    before_matrices = fw.matrices.copy()
    before = {key: value for key, value in fw.matrices.items() if key[0] != profile}
    result = kb.set_snap(9, 21)
    assert result == {"changed": True, "profile": profile, "slots": [9, 21], "paired": True}
    writes = [command for command in fw.sent if command[0] in (0x0A, 0x65)]
    assert fw.fields[7][9] == fw.fields[7][21] == 7 | 0x80
    assert fw.fields[9][9] == 21 and fw.fields[9][21] == 9
    assert [command[0] for command in writes[-4:]] == [0x65] * 4
    assert (
        writes[-4].hex()
        == "650700090000008a8700000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    )
    assert (
        writes[-3].hex()
        == "650700150000007e8700000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    )
    assert (
        writes[-2].hex()
        == "65090009000000881500000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    )
    assert writes[-1].hex() == "650900150100007b0900" + "00" * 54
    assert fw.matrices[(profile, 0)][9 * 4 : 9 * 4 + 4] == bytes.fromhex("00000400")
    assert fw.matrices[(profile, 0)][21 * 4 : 21 * 4 + 4] == bytes.fromhex("00000700")
    for mode in (1, 2, 3):
        assert fw.matrices[(profile, mode)][9 * 4 : 9 * 4 + 4] == bytes(4)
        assert fw.matrices[(profile, mode)][21 * 4 : 21 * 4 + 4] == bytes(4)
    assert (
        fw.matrices[(profile, 0)][10 * 4 : 10 * 4 + 4]
        == before_matrices[(profile, 0)][10 * 4 : 10 * 4 + 4]
    )
    assert all(fw.matrices[key] == value for key, value in before.items())


def test_snap_clear_preserves_reciprocal_links_and_key_parameters():
    fw = Firmware()
    _make_advanced(fw, 0)
    kb = keyboard(fw)
    kb.identify()
    kb.set_snap(9, 21)
    fw.fields[0] = bytes(bytearray(fw.fields[0]))
    fw.fields[0] = fw.fields[0][:18] + b"\x34\x12" + fw.fields[0][20:]
    before_fields = fw.fields.copy()
    result = kb.clear_snap(9)
    assert result == {"changed": True, "profile": 0, "slots": [9, 21], "paired": False}
    assert fw.fields[7][9] == fw.fields[7][21] == 0x80
    assert fw.fields[9] == before_fields[9]
    assert fw.fields[0] == before_fields[0]
    assert fw.matrices[(0, 1)][9 * 4 : 9 * 4 + 4] == bytes(4)
    assert fw.matrices[(0, 2)][21 * 4 : 21 * 4 + 4] == bytes(4)


def test_snap_clear_resets_custom_normal_bindings():
    fw = Firmware()
    for mode in range(4):
        for slot, action in ((9, bytes((0x40 + mode,) * 4)), (21, bytes((0x50 + mode,) * 4))):
            data = bytearray(fw.matrices[(0, mode)])
            data[slot * 4 : slot * 4 + 4] = action
            fw.matrices[(0, mode)] = bytes(data)
    kb = keyboard(fw)
    kb.identify()
    kb.set_snap(9, 21)
    kb.clear_snap(9)
    assert fw.matrices[(0, 0)][9 * 4 : 9 * 4 + 4] == bytes.fromhex("00000400")
    assert fw.matrices[(0, 0)][21 * 4 : 21 * 4 + 4] == bytes.fromhex("00000700")
    for mode in (1, 2, 3):
        assert fw.matrices[(0, mode)][9 * 4 : 9 * 4 + 4] == bytes(4)
        assert fw.matrices[(0, mode)][21 * 4 : 21 * 4 + 4] == bytes(4)


def test_snap_existing_pair_is_noop_and_unpaired_clear_is_noop():
    fw = Firmware()
    kb = keyboard(fw)
    kb.identify()
    kb.set_snap(9, 21)
    sent = len(fw.sent)
    assert kb.set_snap(9, 21)["changed"] is False
    assert len(fw.sent) == sent
    assert kb.clear_snap(1)["changed"] is False
    assert len(fw.sent) == sent


@pytest.mark.parametrize(
    "call",
    [
        lambda kb: kb.set_snap(9, 9),
        lambda kb: kb.set_snap(0, 9),
        lambda kb: kb.set_snap(9, 128),
        lambda kb: kb.set_snap(True, 9),
        lambda kb: kb.set_snap(77, 9),
    ],
)
def test_snap_rejects_invalid_slots_before_writes(call):
    fw = Firmware()
    kb = keyboard(fw)
    kb.identify()
    sent = len(fw.sent)
    with pytest.raises(ValueError):
        call(kb)
    assert len(fw.sent) == sent


def test_snap_rejects_malformed_existing_link_without_mutation():
    fw = Firmware()
    modes = bytearray(fw.fields[7])
    modes[9] = modes[21] = 7
    fw.fields[7] = bytes(modes)
    links = bytearray(fw.fields[9])
    links[9] = 21
    links[21] = 20
    fw.fields[9] = bytes(links)
    kb = keyboard(fw)
    kb.identify()
    sent = len(fw.sent)
    with pytest.raises(ValueError):
        kb.clear_snap(9)
    assert len(fw.sent) == sent


@pytest.mark.parametrize("kind", ["third", "unknown", "out_of_range"])
def test_snap_rejects_busy_or_malformed_pair_references(kind):
    fw = Firmware()
    modes = bytearray(fw.fields[7])
    links = bytearray(fw.fields[9])
    if kind == "third":
        modes[9] = modes[21] = modes[30] = 7
        links[30] = 9
    elif kind == "unknown":
        modes[9] = 0x66
    else:
        modes[9] = modes[21] = 7
        links[9] = 127
        links[21] = 9
    fw.fields[7] = bytes(modes)
    fw.fields[9] = bytes(links)
    kb = keyboard(fw)
    kb.identify()
    with pytest.raises(ValueError):
        kb.clear_snap(9) if kind != "unknown" else kb.set_snap(9, 21)


def test_snap_readback_and_partial_send_failures_are_reported():
    fw = Firmware()
    fw.corrupt_mode_neighbor = True
    kb = keyboard(fw)
    kb.identify()
    with pytest.raises(ProtocolError):
        kb.set_snap(9, 21)
    fw = Firmware()
    fw.fail_on_send_index = 1
    kb = keyboard(fw)
    kb.identify()
    with pytest.raises(RuntimeError):
        kb.set_snap(9, 21)
    assert len(fw.sent) == 1


def test_snap_profile_change_before_and_after_write_is_reported():
    fw = Firmware()
    fw.change_profile_on_read = True
    fw.change_profile_on_query = 2
    kb = keyboard(fw)
    with pytest.raises(ProtocolError, match="before snap write"):
        kb.set_snap(9, 21)
    assert not any(command[0] in (0x0A, 0x65) for command in fw.sent)

    fw = Firmware()
    fw.change_profile_on_read = True
    fw.change_profile_on_query = 3
    kb = keyboard(fw)
    with pytest.raises(ProtocolError, match="during snap write"):
        kb.set_snap(9, 21)


@pytest.mark.parametrize("product", [0x502C, 0x502E])
def test_snap_cli_pair_and_clear(product, tmp_path, monkeypatch, capsys):
    model = 3727 if product == 0x502C else 3759
    fw = Firmware(model_id=model)
    info = DeviceInfo(
        "/dev/he-snap",
        "HE60 Lite",
        3,
        0x3151,
        product,
        bytes.fromhex("06ffff0902a10175089540b102c0"),
        "usb",
        0,
    )
    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: keyboard(fw, product=product).transport)
    assert cli.main(["--device", info.path, "snap", "9", "21"]) == 0
    assert json.loads(capsys.readouterr().out)["paired"] is True
    assert cli.main(["--device", info.path, "snap-clear", "9"]) == 0
    assert json.loads(capsys.readouterr().out)["paired"] is False


@pytest.mark.parametrize("paired", [False, True])
def test_snap_noop_rejects_profile_change(paired):
    fw = Firmware()
    kb = keyboard(fw)
    if paired:
        kb.set_snap(9, 21)
    sent = len(fw.sent)
    original = fw.exchange
    count = 0

    def exchange(command):
        nonlocal count
        if command[0] == 0x84:
            count += 1
            if count == 3:
                fw.profile = 1
        return original(command)

    fw.exchange = exchange
    with pytest.raises(ProtocolError, match="before snap operation"):
        kb.set_snap(9, 21) if paired else kb.clear_snap(9)
    assert len(fw.sent) == sent


def test_snap_rejects_third_reference_to_otherwise_reciprocal_pair():
    fw = Firmware()
    kb = keyboard(fw)
    kb.set_snap(9, 21)
    modes = bytearray(fw.fields[7])
    links = bytearray(fw.fields[9])
    modes[30], links[30] = 7, 9
    fw.fields[7], fw.fields[9] = bytes(modes), bytes(links)
    sent = len(fw.sent)
    with pytest.raises(ValueError, match="another snap key"):
        kb.clear_snap(9)
    assert len(fw.sent) == sent


@pytest.mark.parametrize("damage", ["link", "matrix"])
def test_snap_detects_lost_link_or_unrelated_matrix_damage(damage):
    fw = Firmware()
    kb = keyboard(fw)
    original = fw.send

    def send(command):
        if damage == "link" and command[:4] == bytes([0x65, 9, 0, 21]):
            return
        result = original(command)
        if damage == "matrix" and command[:4] == bytes([0x65, 9, 0, 21]):
            raw = bytearray(fw.matrices[(0, 3)])
            raw[4] ^= 1
            fw.matrices[(0, 3)] = bytes(raw)
        return result

    fw.send = send
    with pytest.raises(ProtocolError, match="snap readback differs"):
        kb.set_snap(9, 21)


def test_snap_normal_pair_preserves_maps_until_clear_restores_both_keys():
    fw = Firmware()
    kb = keyboard(fw)
    before = fw.matrices.copy()
    kb.set_snap(9, 21)
    assert fw.matrices == before
    kb.clear_snap(21)
    expected = before.copy()
    for submode in range(4):
        raw = bytearray(before[(0, submode)])
        raw[36:40] = bytes.fromhex("00000400") if submode == 0 else bytes(4)
        raw[84:88] = bytes.fromhex("00000700") if submode == 0 else bytes(4)
        expected[(0, submode)] = bytes(raw)
    assert fw.matrices == expected
