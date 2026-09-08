"""CommonMSCH585 USB mouse workflows against the public Mouse API."""

from __future__ import annotations

import copy

import pytest

from epomaker_driver.errors import ProtocolError, UnsupportedDevice
from epomaker_driver.mouse import PRODUCTS, Mouse
from epomaker_driver.transport import Transport


class MouseFirmware:
    def __init__(self, model_id=3961):
        self.model_id = model_id
        self.usb_version = 0x0400
        self.profile = 0
        self.sent = []
        self.query_log = []
        self.drop_profile = False
        self.drop_dpi = False
        self.corrupt_dpi = False
        self.corrupt_dpi_after_write = False
        self.corrupt_matrix = False
        self.corrupt_matrix_after_write = False
        self.drop_matrix = False
        self.matrix = {
            (profile, slot): bytes([(profile + slot) & 255, 1, 2, 3])
            for profile in range(8)
            for slot in range(16)
        }
        self.levels = []
        for slot in range(8):
            self.levels.append(
                {"x": 800 + slot * 100, "y": 800 + slot * 100, "rgb": 0x101010 + slot}
            )
        self.current = 1
        self.count = 7 if model_id == 3929 else 6
        self.dpi_banks = {
            p: {"levels": copy.deepcopy(self.levels), "current": self.current, "count": self.count}
            for p in range(8)
        }
        self.report_rate = 1000
        self.macros = {slot: bytes(256) for slot in range(50)}
        self.corrupt_macro = False
        self.drop_macro = False

    @property
    def product_id(self):
        return next(pid for pid, ids in PRODUCTS.items() if self.model_id in ids)

    def exchange(self, command):
        self.query_log.append(bytes(command))
        op = command[0]
        if op == 0x8F:
            raw = bytearray(64)
            raw[0] = op
            raw[1:5] = self.model_id.to_bytes(4, "little")
            raw[5:7] = self.usb_version.to_bytes(2, "little")
            return bytes(raw)
        if op == 0x82:
            return bytes([op, self.profile]) + bytes(62)
        if op == 0x81:
            raw = bytearray(64)
            for slot in range(16):
                raw[slot * 4 : slot * 4 + 4] = self.matrix[(command[1], slot)]
            if self.corrupt_matrix or (self.corrupt_matrix_after_write and self.sent):
                raw[0] ^= 1
            return bytes(raw)
        if op == 0x90:
            bank = self.dpi_banks[command[1]]
            levels = self.levels if command[1] == 0 else bank["levels"]
            current = self.current if command[1] == 0 else bank["current"]
            count = self.count if command[1] == 0 else bank["count"]
            raw = bytearray(64)
            raw[:4] = bytes([op, command[1], current, count])
            raw[4:7] = bytes.fromhex("5aa53c")
            for slot, level in enumerate(levels):
                raw[8 + slot * 2 : 10 + slot * 2] = level["x"].to_bytes(2, "little")
                raw[24 + slot * 2 : 26 + slot * 2] = level["y"].to_bytes(2, "little")
                raw[40 + slot * 3 : 43 + slot * 3] = level["rgb"].to_bytes(3, "big")
            if self.corrupt_dpi or (self.corrupt_dpi_after_write and self.sent):
                raw[8] ^= 1
            return bytes(raw)
        if op == 0x88:
            return bytes(
                [
                    op,
                    {125: 8, 250: 4, 500: 2, 1000: 1, 2000: 132, 4000: 130, 8000: 129}[
                        self.report_rate
                    ],
                ]
            ) + bytes(62)
        if op == 0x9F:
            raw = bytearray(64)
            raw[0] = op
            raw[8] = self.profile
            raw[9] = 10
            raw[15] = {125: 8, 250: 4, 500: 2, 1000: 1, 2000: 132, 4000: 130, 8000: 129}[
                self.report_rate
            ]
            return bytes(raw)
        if op == 0x83:
            slot, page = command[1], command[2]
            raw = bytearray(self.macros[slot][page * 64 : (page + 1) * 64])
            if self.corrupt_macro and page == 3:
                raw[0] ^= 1
            return bytes(raw)
        raise AssertionError(f"unexpected mouse query {op:#x}")

    def send(self, command):
        self.sent.append(bytes(command))
        op = command[0]
        if op == 0x02:
            if not self.drop_profile:
                self.profile = command[1]
        elif op == 0x00:
            if not self.drop_profile:
                slot = command[1]
                self.matrix[(self.profile, slot)] = bytes(command[8:12])
        elif op == 0x01:
            if not self.drop_matrix:
                profile, chunk = command[1], command[2]
                current = bytearray(b"".join(self.matrix[(profile, slot)] for slot in range(16)))
                current[chunk * 56 : (chunk + 1) * 56] = command[8:64]
                for slot in range(16):
                    start = slot * 4
                    self.matrix[(profile, slot)] = bytes(current[start : start + 4])
        elif op == 0x10:
            if not self.drop_dpi:
                assert command[4:7] == bytes(3)
                bank = self.dpi_banks[command[1]]
                bank["current"] = command[2]
                bank["count"] = command[3]
                if command[1] == 0:
                    self.current, self.count = command[2], command[3]
                for slot in range(8):
                    level = {
                        "x": int.from_bytes(command[8 + slot * 2 : 10 + slot * 2], "little"),
                        "y": int.from_bytes(command[24 + slot * 2 : 26 + slot * 2], "little"),
                        "rgb": int.from_bytes(command[40 + slot * 3 : 43 + slot * 3], "big"),
                    }
                    bank["levels"][slot] = level
                    if command[1] == 0:
                        self.levels[slot] = level
        elif op == 0x08:
            self.report_rate = {8: 125, 4: 250, 2: 500, 1: 1000, 132: 2000, 130: 4000, 129: 8000}[
                command[1]
            ]
        elif op == 0x03:
            if not self.drop_macro:
                slot, chunk = command[1], command[2]
                data = bytearray(self.macros[slot])
                end = min(256, chunk * 56 + 56)
                data[chunk * 56 : end] = command[8 : 8 + end - chunk * 56]
                self.macros[slot] = bytes(data)
        else:
            raise AssertionError(f"unexpected mouse write {op:#x}")


class USB:
    def __init__(self, firmware):
        self.firmware = firmware
        self.response = bytes(64)

    def set_feature(self, data):
        assert len(data) == 65 and data[0] == 0
        command = data[1:]
        self.response = self.firmware.exchange(command) if command[0] >= 0x80 else bytes(64)
        if command[0] < 0x80:
            self.firmware.send(command)

    def get_feature(self, report_id, length):
        assert report_id == 0 and length == 64
        return self.response

    def close(self):
        pass


def mouse_keyboard(model_id=3961):
    firmware = MouseFirmware(model_id)
    transport = Transport(USB(firmware), "usb", sleep=lambda _: None)
    return Mouse(transport, product_id=firmware.product_id), firmware


@pytest.mark.parametrize("model_id", [3961, 3303, 3304, 3929, 3919])
def test_identity_and_model_gates(model_id):
    keyboard, firmware = mouse_keyboard(model_id)
    value = keyboard.identify()
    assert value["device_id"] == model_id
    assert value["usb_version"] == 0x0400
    assert value["is_boot"] is None
    assert keyboard.get_dpi()["raw"][0] == 0x90


def test_wrong_internal_identity_is_rejected_before_other_commands():
    keyboard, firmware = mouse_keyboard(3961)
    firmware.model_id = 3303
    with pytest.raises(UnsupportedDevice):
        keyboard.status()
    assert firmware.sent == []


@pytest.mark.parametrize("profile", range(8))
def test_profile_selection_readback(profile):
    keyboard, firmware = mouse_keyboard()
    keyboard.set_profile(profile)
    assert firmware.profile == profile
    assert keyboard.get_profile() == profile


def test_profile_drop_is_detected():
    keyboard, firmware = mouse_keyboard()
    firmware.drop_profile = True
    with pytest.raises(ProtocolError):
        keyboard.set_profile(2)


def test_macro_read_returns_all_four_raw_pages():
    keyboard, firmware = mouse_keyboard()
    firmware.macros[7] = bytes(range(256))
    assert keyboard.read_macro(7) == bytes(range(256))
    assert [command[:3] for command in firmware.query_log if command[0] == 0x83] == [
        bytes([0x83, 7, page]) for page in range(4)
    ]


def test_macro_write_sends_five_contiguous_chunks_and_preserves_zero_holes():
    keyboard, firmware = mouse_keyboard()
    data = bytearray(256)
    data[3] = 17
    data[112] = 29  # A later chunk is nonzero while an earlier one is empty.
    result = keyboard.write_macro(7, bytes(data))
    assert result == {"slot": 7, "profile": 0, "changed": True}
    writes = [command for command in firmware.sent if command[0] == 3]
    assert len(writes) == 5
    assert [command[2] for command in writes] == list(range(5))
    assert all(command[3] == 56 for command in writes)
    assert writes[-1][4] == 1
    assert all(command[4] == 0 for command in writes[:-1])
    assert all(command[7] == (255 - sum(command[:7])) & 255 for command in writes)
    assert firmware.macros[7] == bytes(data)


def test_macro_write_noop_sends_no_configuration_packets():
    keyboard, firmware = mouse_keyboard()
    data = bytes([4]) * 256
    firmware.macros[3] = data
    assert keyboard.write_macro(3, data)["changed"] is False
    assert not [command for command in firmware.sent if command[0] == 3]


def test_macro_write_clears_existing_nonzero_storage_with_all_chunks():
    keyboard, firmware = mouse_keyboard()
    firmware.macros[4] = bytes([9]) * 256
    assert keyboard.write_macro(4, bytes(256))["changed"] is True
    assert firmware.macros[4] == bytes(256)
    assert len([command for command in firmware.sent if command[0] == 3]) == 5


def test_macro_allocator_accepts_slot_49():
    keyboard, firmware = mouse_keyboard()
    data = bytes([7]) * 256
    firmware.macros[49] = data
    assert keyboard.read_macro(49) == data
    with pytest.raises(ValueError):
        keyboard.read_macro(50)
    with pytest.raises(ValueError):
        keyboard.write_macro(50, data)
    assert not [command for command in firmware.sent if command[0] == 3]


def test_macro_noop_checks_profile_before_return(monkeypatch):
    keyboard, firmware = mouse_keyboard()
    data = bytes([4]) * 256
    firmware.macros[3] = data
    profiles = iter((0, 1))
    monkeypatch.setattr(keyboard, "get_profile", lambda: next(profiles))
    with pytest.raises(ProtocolError, match="before macro write"):
        keyboard.write_macro(3, data)
    assert not [command for command in firmware.sent if command[0] == 3]


def test_macro_profile_drift_stops_before_next_chunk(monkeypatch):
    keyboard, firmware = mouse_keyboard()
    profiles = iter((0, 0, 0, 1))
    monkeypatch.setattr(keyboard, "get_profile", lambda: next(profiles))
    with pytest.raises(ProtocolError, match="before macro write"):
        keyboard.write_macro(0, bytes([8]) * 256)
    writes = [command for command in firmware.sent if command[0] == 3]
    assert len(writes) == 1


@pytest.mark.parametrize("slot", [-1, 50, 256, True])
def test_macro_slot_bounds_reject_before_io(slot):
    keyboard, firmware = mouse_keyboard()
    with pytest.raises(ValueError):
        keyboard.read_macro(slot)
    with pytest.raises(ValueError):
        keyboard.write_macro(slot, bytes(256))
    assert firmware.sent == []


@pytest.mark.parametrize("data", [bytearray(256), bytes(255), bytes(257), "x"])
def test_macro_write_requires_raw_256_byte_bytes(data):
    keyboard, firmware = mouse_keyboard()
    with pytest.raises(ValueError):
        keyboard.write_macro(0, data)
    assert firmware.sent == []


def test_macro_write_readback_failure_is_reported():
    keyboard, firmware = mouse_keyboard()
    firmware.corrupt_macro = True
    with pytest.raises(ProtocolError, match="macro readback"):
        keyboard.write_macro(0, bytes([8]) * 256)


def test_macro_write_drop_is_reported():
    keyboard, firmware = mouse_keyboard()
    firmware.drop_macro = True
    with pytest.raises(ProtocolError, match="macro readback"):
        keyboard.write_macro(0, bytes([8]) * 256)


def test_matrix_raw_response_and_key_write_preserve_neighbors():
    keyboard, firmware = mouse_keyboard()
    before = keyboard.read_matrix(0)
    assert before[0] == 0
    action = bytes.fromhex("10203040")
    keyboard.set_key(5, action)
    after = keyboard.read_matrix(0)
    assert after[20:24] == action
    assert after[:20] == before[:20]
    assert after[24:] == before[24:]
    assert firmware.sent[-1][0] == 0


@pytest.mark.parametrize("slot", [-1, 16])
def test_nonphysical_key_slot_rejected_without_write(slot):
    keyboard, firmware = mouse_keyboard()
    with pytest.raises(ValueError):
        keyboard.set_key(slot, b"1234")
    assert firmware.sent == []


def test_matrix_corruption_is_detected():
    keyboard, firmware = mouse_keyboard()
    firmware.corrupt_matrix_after_write = True
    with pytest.raises(ProtocolError):
        keyboard.set_key(1, b"1234")


@pytest.mark.parametrize("profile", range(8))
def test_matrix_write_restores_all_profiles_in_two_chunks(profile):
    keyboard, firmware = mouse_keyboard()
    data = bytes((profile * 17 + offset) & 255 for offset in range(64))
    result = keyboard.write_matrix(profile, data)
    assert result == {"profile": profile, "changed": True}
    assert keyboard.read_matrix(profile) == data
    assert firmware.profile == 0
    writes = [command for command in firmware.sent if command[0] == 1]
    assert len(writes) == 2
    assert [command[1:3] for command in writes] == [bytes([profile, 0]), bytes([profile, 1])]
    assert all(command[7] == (255 - sum(command[:7])) & 255 for command in writes)


def test_matrix_write_pads_second_chunk_and_preserves_exact_payload():
    keyboard, firmware = mouse_keyboard()
    data = bytes(range(64))
    keyboard.write_matrix(2, data)
    writes = [command for command in firmware.sent if command[0] == 1]
    assert writes[0][8:] == data[:56]
    assert writes[1][8:16] == data[56:]
    assert writes[1][16:] == bytes(48)


@pytest.mark.parametrize("data", [bytearray(64), bytes(63), bytes(65), "x"])
def test_matrix_write_requires_raw_64_byte_bytes(data):
    keyboard, firmware = mouse_keyboard()
    with pytest.raises(ValueError):
        keyboard.write_matrix(0, data)
    assert firmware.sent == []


@pytest.mark.parametrize("profile", [-1, 8, True])
def test_matrix_write_profile_bounds_reject_before_io(profile):
    keyboard, firmware = mouse_keyboard()
    with pytest.raises(ValueError):
        keyboard.write_matrix(profile, bytes(64))
    assert firmware.sent == []


def test_matrix_write_noop_skips_packets_and_preserves_active_profile():
    keyboard, firmware = mouse_keyboard()
    firmware.profile = 3
    data = keyboard.read_matrix(6)
    firmware.sent.clear()
    assert keyboard.write_matrix(6, data) == {"profile": 6, "changed": False}
    assert firmware.profile == 3
    assert not [command for command in firmware.sent if command[0] == 1]


@pytest.mark.parametrize("failure", ["drop_matrix", "corrupt_matrix_after_write"])
def test_matrix_write_reports_partial_state_on_write_or_readback_failure(failure):
    keyboard, firmware = mouse_keyboard()
    setattr(firmware, failure, True)
    with pytest.raises(ProtocolError, match=r"profile 4.*partially written"):
        keyboard.write_matrix(4, bytes([8]) * 64)


def test_matrix_write_detects_profile_drift_on_noop(monkeypatch):
    keyboard, firmware = mouse_keyboard()
    data = keyboard.read_matrix(2)
    profiles = iter((0, 1))
    monkeypatch.setattr(keyboard, "get_profile", lambda: next(profiles))
    with pytest.raises(ProtocolError, match="profile 2"):
        keyboard.write_matrix(2, data)
    assert not [command for command in firmware.sent if command[0] == 1]


def test_dpi_patch_preserves_all_other_levels_and_rgb():
    keyboard, firmware = mouse_keyboard(3961)
    before = keyboard.get_dpi()
    keyboard.set_dpi(slot=2, x=32500, y=32500, rgb=0xABCDEF)
    after = keyboard.get_dpi()
    assert after["levels"][2] == {"x": 32500, "y": 32500, "rgb": 0xABCDEF}
    assert after["levels"][:2] == before["levels"][:2]
    assert after["levels"][3:] == before["levels"][3:]
    assert firmware.sent[-1][0] == 0x10


@pytest.mark.parametrize(
    "model_id,value",
    [
        (3961, 32500),
        (3304, 15000),
        (3303, 10000),
        (3303, 12000),
        (3929, 26000),
        (3919, 10000),
        (3919, 16000),
    ],
)
def test_model_specific_dpi_boundaries(model_id, value):
    keyboard, firmware = mouse_keyboard(model_id)
    keyboard.set_dpi(slot=0, x=value, y=value)
    assert firmware.levels[0]["x"] == value


@pytest.mark.parametrize(
    "model_id,value",
    [
        (3961, 32501),
        (3304, 15050),
        (3303, 10050),
        (3303, 12050),
        (3929, 26050),
        (3919, 10050),
        (3919, 16050),
    ],
)
def test_invalid_dpi_step_rejected_before_write(model_id, value):
    keyboard, firmware = mouse_keyboard(model_id)
    with pytest.raises(ValueError):
        keyboard.set_dpi(slot=0, x=value)
    assert firmware.sent == []


def test_dpi_readback_drop_and_corruption_are_detected():
    keyboard, firmware = mouse_keyboard()
    firmware.drop_dpi = True
    with pytest.raises(ProtocolError):
        keyboard.set_dpi(slot=1, x=1250, y=1250)
    firmware.drop_dpi = False
    firmware.corrupt_dpi_after_write = True
    with pytest.raises(ProtocolError):
        keyboard.set_dpi(slot=1, x=1250, y=1250)


def test_dpi_current_falls_back_when_disabling_active_level():
    keyboard, firmware = mouse_keyboard()
    firmware.current = 1
    keyboard.set_dpi(slot=1, x=0, y=0)
    assert firmware.current == 0


def test_invalid_current_and_unknown_baseline_are_rejected():
    keyboard, firmware = mouse_keyboard()
    with pytest.raises(ValueError):
        keyboard.set_dpi(current=6)
    assert firmware.sent == []
    firmware.current = 7
    with pytest.raises(ValueError):
        keyboard.set_dpi(slot=0, x=900)
    assert firmware.sent == []


@pytest.mark.parametrize("hz", [125, 250, 500, 1000, 2000, 4000, 8000])
def test_report_rate_roundtrip(hz):
    keyboard, firmware = mouse_keyboard(3961)
    keyboard.set_rate(hz)
    assert firmware.report_rate == hz
    assert keyboard.status()["settings"]["report_rate"] == hz


def test_report_rate_pid_5043_is_limited_to_1000():
    keyboard, firmware = mouse_keyboard(3303)
    keyboard.set_rate(1000)
    with pytest.raises(ValueError):
        keyboard.set_rate(2000)
    assert firmware.report_rate == 1000


def test_unknown_matrix_opcode_is_raw_and_not_interpreted():
    keyboard, firmware = mouse_keyboard()
    firmware.matrix[(0, 0)] = bytes([0x90, 2, 3, 4])
    assert keyboard.read_matrix()[0] == 0x90


def test_constructor_rejects_unsupported_transport_and_product():
    firmware = MouseFirmware()
    with pytest.raises(UnsupportedDevice):
        Mouse(Transport(USB(firmware), "bluetooth", sleep=lambda _: None), product_id=0x503A)
    with pytest.raises(UnsupportedDevice):
        Mouse(Transport(USB(firmware), "usb", sleep=lambda _: None), product_id=0xFFFF)


def test_cached_identity_mismatch_is_rejected():
    keyboard, firmware = mouse_keyboard()
    keyboard.identify()
    keyboard.identity["device_id"] = 3303
    with pytest.raises(UnsupportedDevice):
        keyboard.get_profile()


def test_invalid_profile_response_is_rejected():
    keyboard, firmware = mouse_keyboard()
    firmware.profile = 8
    with pytest.raises(ProtocolError):
        keyboard.get_profile()


@pytest.mark.parametrize("action", [b"123", [1, 2, 3, 4], bytearray(b"1234")])
def test_key_action_requires_exact_bytes(action):
    keyboard, firmware = mouse_keyboard()
    with pytest.raises(ValueError):
        keyboard.set_key(1, action)
    assert firmware.sent == []


def test_key_requested_profile_must_be_active():
    keyboard, firmware = mouse_keyboard()
    with pytest.raises(ValueError):
        keyboard.set_key(1, b"1234", profile=1)
    assert firmware.sent == []


def test_key_profile_drift_before_write_is_detected():
    keyboard, firmware = mouse_keyboard()
    original = keyboard.get_profile
    calls = 0

    def drift():
        nonlocal calls
        calls += 1
        if calls == 2:
            firmware.profile = 1
        return original()

    keyboard.get_profile = drift
    with pytest.raises(ProtocolError):
        keyboard.set_key(1, b"1234")
    assert firmware.sent == []


def test_empty_and_below_minimum_dpi_requests_are_rejected_before_io():
    keyboard, firmware = mouse_keyboard()
    with pytest.raises(ValueError):
        keyboard.set_dpi()
    with pytest.raises(ValueError):
        keyboard.set_dpi(slot=0, x=25)
    assert firmware.sent == []


def test_dpi_rejects_mixed_zero_axes():
    keyboard, firmware = mouse_keyboard()
    with pytest.raises(ValueError):
        keyboard.set_dpi(slot=0, x=0, y=900)
    assert firmware.sent == []


def test_dpi_partial_channel_patches_preserve_other_channels():
    keyboard, firmware = mouse_keyboard()
    before = keyboard.get_dpi()["levels"][2].copy()
    keyboard.set_dpi(slot=2, x=1250)
    assert keyboard.get_dpi()["levels"][2] == {**before, "x": 1250}
    keyboard.set_dpi(slot=2, rgb=0xABCDEF)
    assert keyboard.get_dpi()["levels"][2] == {**before, "x": 1250, "rgb": 0xABCDEF}


def test_key_noop_does_not_send():
    keyboard, firmware = mouse_keyboard()
    current = keyboard.read_matrix()[4:8]
    keyboard.set_key(1, current)
    assert firmware.sent == []


def test_report_rate_readback_failure_is_detected():
    keyboard, firmware = mouse_keyboard()
    original = firmware.send

    def drop_rate(command):
        if command[0] != 0x08:
            original(command)

    firmware.send = drop_rate
    with pytest.raises(ProtocolError):
        keyboard.set_rate(500)


def test_status_profile_drift_is_detected():
    keyboard, firmware = mouse_keyboard()
    original = keyboard.get_profile
    calls = 0

    def drift():
        nonlocal calls
        calls += 1
        if calls >= 2:
            firmware.profile = 1
        result = original()
        return result

    keyboard.get_profile = drift
    with pytest.raises(ProtocolError):
        keyboard.status()


def test_dpi_edits_address_the_requested_profile_bank_only():
    mouse, fw = mouse_keyboard()
    before = mouse.get_dpi(0)
    mouse.set_dpi(7, slot=1, x=1600, y=1600)
    assert mouse.get_dpi(7)["levels"][1]["x"] == 1600
    assert mouse.get_dpi(0) == before
    assert fw.profile == 0


@pytest.mark.parametrize(
    "error", [OSError("disconnected"), ProtocolError("bad reply"), KeyboardInterrupt()]
)
def test_macro_partial_failure_preserves_error_context(monkeypatch, error):
    mouse, fw = mouse_keyboard()
    original = fw.send

    def fail(command):
        if command[0] == 3 and command[2] == 2:
            raise error
        original(command)

    monkeypatch.setattr(fw, "send", fail)
    with pytest.raises(ProtocolError, match="slot 2.*partially") as caught:
        mouse.write_macro(2, bytes([5]) * 256)
    assert caught.value.__cause__ is error
    assert len(fw.sent) == 2


def test_macro_read_profile_drift_is_detected(monkeypatch):
    mouse, fw = mouse_keyboard()
    profiles = iter([0, 1])
    monkeypatch.setattr(mouse, "get_profile", lambda: next(profiles))
    with pytest.raises(ProtocolError, match="macro read"):
        mouse.read_macro(0)


def test_macro_final_profile_drift_reports_partial_state(monkeypatch):
    mouse, fw = mouse_keyboard()
    profiles = iter([0] * 7 + [1])
    monkeypatch.setattr(mouse, "get_profile", lambda: next(profiles))
    with pytest.raises(ProtocolError, match="during macro write.*partially"):
        mouse.write_macro(0, bytes([1]) * 256)


def test_macro_raw_page_shape_is_checked(monkeypatch):
    mouse, fw = mouse_keyboard()
    original = mouse.transport.exchange
    monkeypatch.setattr(
        mouse.transport,
        "exchange",
        lambda command, **kw: bytes(63) if command[0] == 0x83 else original(command, **kw),
    )
    with pytest.raises(ProtocolError, match="64 bytes"):
        mouse.read_macro(0)


def test_macro_write_preserves_other_slots_and_keymaps():
    mouse, fw = mouse_keyboard()
    fw.macros[1] = bytes([13]) * 256
    fw.profile = 7
    matrices = fw.matrix.copy()
    before = fw.macros.copy()
    data = bytes(range(256))
    mouse.write_macro(49, data)
    before[49] = data
    assert fw.macros == before
    assert fw.matrix == matrices
    assert fw.profile == 7


def test_macro_mutation_reidentifies_before_configuration_writes():
    mouse, fw = mouse_keyboard()
    mouse.identify()
    fw.model_id = 3303
    with pytest.raises(UnsupportedDevice):
        mouse.write_macro(0, bytes(256))
    assert not fw.sent
