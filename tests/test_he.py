import json

import pytest

from epomaker_driver import cli, codec
from epomaker_driver.discovery import DeviceInfo
from epomaker_driver.errors import ProtocolError, UnsupportedDevice
from epomaker_driver.he import HEKeyboard
from epomaker_driver.transport import Transport
from epomaker_driver.versions import version_request


class Firmware:
    def __init__(self, model_id=3727, boot=False):
        self.model_id = model_id
        self.boot = boot
        self.usb_version = 0x0400
        self.rf_version = 0x0500
        self.sent = []
        self.query_log = []
        self.profile = 0
        self.short_pages = False
        self.mismatch_key = False
        self.change_profile_on_read = False
        self.profile_query_count = 0
        self.change_profile_on_query = None
        self.drop_magnetic_write = False
        self.corrupt_magnetic_neighbor = False
        self.drop_mode_write = False
        self.corrupt_mode_neighbor = False
        self.change_profile_on_mode_read = False
        self.corrupt_action_after_write = False
        self._action_write_seen = False
        self.fail_on_send_index = None
        self.options = bytearray(64)
        self.options[0] = 0x89
        self.auto_os = False
        self.debounce = 10
        self.sleep = [60, 60, 60, 65535]
        self.drop_sleep_write = False
        self.corrupt_sleep_hidden = False
        self.light = bytearray(64)
        self.light[0] = 0x87
        self.pictures = {index: bytes([index]) * 378 for index in range(5)}
        self.macros = {slot: bytes(256) for slot in range(256)}
        profile_count = (
            4
            if model_id
            in (3662, 3664, 3746, 2762, 2883, 2465, 2586, 2870, 3691, 3692, 3703, 2761, 2959)
            else 2
        )
        self.matrices = {
            (profile, mode): bytes([profile, mode]) * 256
            for profile in range(profile_count)
            for mode in range(4)
        }
        self.fn = {(layer, os): bytes([layer, os]) * 256 for layer in range(2) for os in range(2)}
        self.fields = {
            field: bytes([field]) * 256 for field in (0, 1, 2, 3, 4, 5, 6, 7, 9, 251, 252)
        }
        self.fields[9] = bytes(256)
        self.fields[7] = bytes([0x80, 0x00] * 64)
        self.fields[10] = (
            bytes(range(128))
            + bytes([0x80 + i for i in range(128)])
            + bytes([0x40 + i for i in range(128)])
            + bytes([(0xC0 + i) & 255 for i in range(128)])
        )

    def exchange(self, command):
        self.query_log.append(bytes(command))
        op = command[0]
        if op == 0x8F:
            raw = bytearray(64)
            raw[0] = op
            raw[1:5] = self.model_id.to_bytes(4, "little")
            raw[7:9] = self.usb_version.to_bytes(2, "little")
            raw[9] = int(self.boot)
            return bytes(raw)
        if op == 0x80:
            raw = bytearray(64)
            raw[0] = op
            raw[1:3] = self.rf_version.to_bytes(2, "little")
            return bytes(raw)
        if op == 0x84:
            raw = bytearray(64)
            raw[0] = op
            raw[1] = self.profile
            self.profile_query_count += 1
            if self.change_profile_on_read and (
                self.change_profile_on_query is None
                or self.profile_query_count >= self.change_profile_on_query
            ):
                self.profile = 1 - self.profile
            return bytes(raw)
        if op == 0x89:
            return bytes(self.options)
        if op == 0x97:
            return bytes([0x97, int(self.auto_os)]) + bytes(62)
        if op == 0x86:
            return bytes([0x86, self.debounce]) + bytes(62)
        if op == 0x91:
            raw = bytearray(64)
            raw[0] = 0x91
            for index, value in enumerate(self.sleep):
                raw[8 + index * 2 : 10 + index * 2] = value.to_bytes(2, "little")
            return bytes(raw)
        if op == 0x87:
            return bytes(self.light)
        if op == 0x8C:
            picture, page = command[1], command[3]
            return self.pictures[picture][page * 64 : (page + 1) * 64].ljust(64, b"\0")
        if op == 0x8A:
            data = self.matrices[(command[1], command[4])]
            result = data[command[3] * 64 : (command[3] + 1) * 64]
            if self.corrupt_action_after_write and self._action_write_seen:
                result = bytes([result[0] ^ 1]) + result[1:]
            return result[:-1] if self.short_pages else result
        if op == 0x90:
            data = self.fn[(command[2], command[1])]
            return data[command[4] * 64 : (command[4] + 1) * 64]
        if op == 0xE5:
            field, page = command[1], command[3]
            source = self.fields[field] if field != 10 else self.fields[10]
            return (source + bytes(512))[page * 64 : (page + 1) * 64]
        if op == 0x8B:
            slot, page = command[1], command[2]
            return self.macros[slot][page * 64 : (page + 1) * 64]
        raise AssertionError(f"unexpected query {op:#x}")

    def send(self, command):
        if self.fail_on_send_index is not None and len(self.sent) == self.fail_on_send_index:
            raise RuntimeError("injected USB send failure")
        self.sent.append(command)
        if command[0] == 0x65:
            assert command[2] == 0 and command[5:7] == bytes(2)
            assert (sum(command[:8]) & 255) == 255
            field, slot = command[1], command[3]
            width = 4 if field == 8 else 1 if field in (5, 7, 9, 251, 252) else 2
            if field == 8:
                if not self.drop_mode_write:
                    trigger = bytearray(self.fields[10])
                    for stage, value in enumerate(command[8:12]):
                        trigger[stage * 128 + slot] = value
                    self.fields[10] = bytes(trigger)
                return
            data = bytearray(self.fields[field])
            if not self.drop_magnetic_write:
                data[slot * width : (slot + 1) * width] = command[8 : 8 + width]
            if self.corrupt_magnetic_neighbor or self.corrupt_mode_neighbor:
                data[((slot + 1) % 128) * width] ^= 1
            self.fields[field] = bytes(data)
        elif command[0] == 0x04:
            self.profile = command[1]
        elif command[0] == 0x09:
            self.options[:] = command
            self.options[0] = 0x89
        elif command[0] == 0x17:
            self.auto_os = bool(command[1])
        elif command[0] == 0x06:
            self.debounce = command[1]
        elif command[0] == 0x11:
            if not self.drop_sleep_write:
                self.sleep = [
                    int.from_bytes(command[8 + i * 2 : 10 + i * 2], "little") for i in range(4)
                ]
                if self.corrupt_sleep_hidden:
                    self.sleep[3] ^= 1
        elif command[0] == 0x07:
            self.light[:] = command
            self.light[0] = 0x87
        elif command[0] == 0x0C:
            picture, page, count = command[1], command[3], command[4]
            data = bytearray(self.pictures[picture])
            data[page * 56 : page * 56 + count] = command[8 : 8 + count]
            self.pictures[picture] = bytes(data)
        elif command[0] == 0x0A:
            self._action_write_seen = True
            profile = command[1]
            if command[2] == 255:
                start = command[3] * 56
                self.matrices[(profile, command[6])] = (
                    self.matrices[(profile, command[6])][:start]
                    + command[8 : 8 + command[4]]
                    + self.matrices[(profile, command[6])][start + command[4] :]
                )
            else:
                matrix = bytearray(self.matrices[(profile, command[6])])
                if not self.mismatch_key:
                    matrix[command[2] * 4 : command[2] * 4 + 4] = command[8:12]
                self.matrices[(profile, command[6])] = bytes(matrix)
        elif command[0] == 0x10:
            key = (command[2], command[1])
            matrix = bytearray(self.fn[key])
            matrix[command[3] * 4 : command[3] * 4 + 4] = command[8:12]
            self.fn[key] = bytes(matrix)
        elif command[0] == 0x0B:
            slot, page = command[1], command[2]
            data = bytearray(self.macros[slot])
            count = min(command[3], 256 - page * 56)
            data[page * 56 : page * 56 + count] = command[8 : 8 + count]
            self.macros[slot] = bytes(data)

    def sleep(self, _):
        pass


def keyboard(firmware, product=0x502C):
    class USB:
        def set_feature(self, data):
            assert len(data) == 65 and data[0] == 0
            self.response = (
                firmware.exchange(data[1:]) if data[1] >= 128 else firmware.send(data[1:])
            )
            if self.response is None:
                self.response = bytes([data[1]]) + bytes(63)

        def get_feature(self, *_):
            assert _ == (0, 64)
            response = getattr(self, "response", bytes(64))
            if not firmware.short_pages:
                assert len(response) == 64
            return response

        def close(self):
            pass

    return HEKeyboard(Transport(USB(), "usb", sleep=lambda _: None), product_id=product)


def test_h60_uses_four_profiles_and_five_picture_banks():
    fw = Firmware(model_id=3662)
    fw.matrices.update(
        {(profile, mode): bytes([profile, mode]) * 256 for profile in (2, 3) for mode in range(4)}
    )
    kb = keyboard(fw, product=0x5029)
    assert kb.identify()["device_id"] == 3662
    assert kb.read_matrix(profile=3, mode=3)[:2] == b"\x03\x03"
    kb.set_profile(3)
    assert kb.write_picture(bytes([0x11, 0x22, 0x33]) * 126, picture=4) is None
    status = kb.status()
    assert status["profiles"] == 4
    assert status["picture_banks"] == 5
    assert "magnetic-read" in status["capabilities"]


def test_h60_same_pid_sibling_is_identified_before_writes():
    fw = Firmware(model_id=3746)
    kb = keyboard(fw, product=0x5029)
    assert kb.identify()["device_id"] == 3746


def test_he_identity_and_matrix_submodes_use_usb():
    fw = Firmware()
    kb = keyboard(fw)
    assert kb.identify()["device_id"] == 3727
    assert kb.read_matrix(mode=3)[:2] == b"\x00\x03"
    assert kb.read_matrix(fn=True, os_mode=1)[:2] == b"\x00\x01"
    assert [command[4] for command in fw.query_log if command[0] == 0x8A][-8:] == [3] * 8


@pytest.mark.parametrize("profile", [0, 1])
@pytest.mark.parametrize("mode", range(4))
def test_he_normal_key_write_isolated_by_profile_and_submode(profile, mode):
    fw = Firmware()
    kb = keyboard(fw)
    kb.identify()
    action = bytes((profile, mode, 0x12, 0x34))
    before = fw.matrices.copy()
    assert kb.set_key(3, action, profile=profile, mode=mode) == list(action)
    assert fw.matrices[(profile, mode)][12:16] == action
    expected = bytearray(before[(profile, mode)])
    expected[12:16] = action
    before[(profile, mode)] = bytes(expected)
    assert fw.matrices == before


@pytest.mark.parametrize("os_mode", [0, 1])
def test_he_fn_write_isolated_by_os(os_mode):
    fw = Firmware()
    kb = keyboard(fw)
    kb.identify()
    action = bytes((9, os_mode, 8, 7))
    before = fw.fn.copy()
    assert kb.set_key(4, action, fn=True, os_mode=os_mode) == list(action)
    expected = bytearray(before[(0, os_mode)])
    expected[16:20] = action
    before[(0, os_mode)] = bytes(expected)
    assert fw.fn == before


def test_he_rejects_invalid_writes_before_transport():
    fw = Firmware()
    kb = keyboard(fw)
    kb.identify()
    before = len(fw.sent)
    with pytest.raises(ValueError):
        kb.set_key(128, b"1234")
    with pytest.raises(ValueError):
        kb.set_key(1, b"1234", mode=4)
    with pytest.raises(ValueError):
        kb.set_key(1, b"1234", fn=True, profile=1)
    with pytest.raises(ValueError):
        kb.set_key(1, b"1234", fn=True, os_mode=2)
    assert len(fw.sent) == before


def test_he_macro_and_profile_roundtrip():
    fw = Firmware()
    kb = keyboard(fw)
    kb.identify()
    data = bytes((index * 7) & 255 for index in range(256))
    kb.write_macro(7, data)
    assert kb.read_macro(7) == data
    shorter = b"\x01\x00" + bytes(254)
    kb.write_macro(7, shorter)
    assert fw.macros[7] == kb.read_macro(7) == shorter
    kb.set_profile(1)
    assert fw.profile == 1
    assert kb.status()["submodes"] == 4


def test_he_magnetic_conditional_reads_and_versions():
    kb = keyboard(Firmware(model_id=3759), product=0x502E)
    value = kb.get_magnetic()
    assert value["versions"] == {"usb": 0x0400, "rf": 0x0500}
    assert {"0", "1", "2", "3", "6", "7", "251"} <= set(value["fields"])
    assert not {"4", "5", "9", "10"} & set(value["fields"])
    assert value["modes"][0] == 0x80


def test_he_magnetic_decodes_all_slots_and_conditional_mode_fields():
    fw = Firmware(model_id=3759)
    modes = bytearray(128)
    modes[:6] = bytes((0x80, 2, 3, 4, 5, 7))
    fw.fields[7] = bytes(modes)
    kb = keyboard(fw, product=0x502E)
    value = kb.get_magnetic()
    assert len(value["slots"]) == 128
    assert [slot["mode"] for slot in value["slots"][:6]] == [
        "normal",
        "dks",
        "mt",
        "tgl_hold",
        "tgl_dots",
        "snap",
    ]
    assert value["slots"][0]["fire"] is True
    assert value["slots"][1]["trigger_modes"] == [1, 129, 65, 193]
    assert value["slots"][1]["travel"] == 0.0
    assert value["slots"][1]["top_deadzone"] == 1.255
    assert {"4", "5", "9", "10"} <= set(value["fields"])


def test_he_wired_does_not_query_rf_version():
    fw = Firmware()
    kb = keyboard(fw)
    value = kb.status()
    assert value["versions"]["rf"] is None
    assert not any(command[0] == 0x80 for command in fw.query_log)


def test_he_fresh_identity_failure_clears_write_authorization():
    fw = Firmware()
    kb = keyboard(fw)
    kb.identify()
    fw.model_id = 3759
    with pytest.raises(UnsupportedDevice):
        kb.status()
    sent = len(fw.sent)
    with pytest.raises(UnsupportedDevice):
        kb.set_key(0, b"1234")
    assert len(fw.sent) == sent


def test_he_wired_rf_query_is_rejected_before_write():
    fw = Firmware()
    kb = keyboard(fw)
    kb.identify()
    with pytest.raises(UnsupportedDevice):
        kb._query(version_request("rf"), expected=0x80)
    assert not any(command[0] == 0x80 for command in fw.sent)


def test_he_short_matrix_page_fails_protocol_check():
    fw = Firmware()
    fw.short_pages = True
    kb = keyboard(fw)
    kb.identify()
    with pytest.raises(ProtocolError, match="unexpected length"):
        kb.read_matrix()


def test_he_rejects_unsupported_product_and_commands():
    with pytest.raises(UnsupportedDevice):
        keyboard(Firmware(), product=0x1234)
    kb = keyboard(Firmware())
    kb.identify()
    with pytest.raises(UnsupportedDevice):
        kb._query(bytes([0xFE]) + bytes(63))
    with pytest.raises(ValueError):
        kb.read_matrix(fn=True, profile=1)


def test_he_key_readback_mismatch_is_protocol_error():
    fw = Firmware()
    fw.mismatch_key = True
    kb = keyboard(fw)
    kb.identify()
    with pytest.raises(ProtocolError, match="readback differs"):
        kb.set_key(2, b"1234")


def test_he_magnetic_profile_change_is_rejected():
    fw = Firmware(model_id=3759)
    fw.change_profile_on_read = True
    kb = keyboard(fw, product=0x502E)
    with pytest.raises(ProtocolError, match="profile changed"):
        kb.get_magnetic()


@pytest.mark.parametrize("product,model", [(0x5029, 3662), (0x502C, 3727), (0x502E, 3759)])
@pytest.mark.parametrize("profile", [0, 1])
@pytest.mark.parametrize(
    "definition",
    [
        {"mode": "normal", "actions": ["00000400"], "travel": 2, "lift": 2.8, "deadzone": 0.3},
        {
            "mode": "dks",
            "actions": ["00000400", "00000500", "00000600", "00000700"],
            "dynamic_travel": 0.7,
            "trigger_modes": [1, 2, 3, 4],
        },
        {"mode": "mt", "actions": ["00000400", "00000500"], "mt_time": 200},
        {"mode": "tgl_hold", "actions": ["00000400"]},
        {"mode": "tgl_dots", "actions": ["00000500"]},
    ],
)
def test_he_magnetic_mode_usb_roundtrip(product, model, profile, definition):
    fw = Firmware(model_id=model)
    kb = keyboard(fw, product=product)
    kb.identify()
    if profile:
        kb.set_profile(profile)
    before_matrices = fw.matrices.copy()
    before_fields = fw.fields.copy()
    result = kb.set_magnetic_mode(5, definition)
    assert result["changed"] is True
    assert fw.profile == profile
    count = len(definition["actions"])
    for submode, action in enumerate(definition["actions"]):
        expected = bytearray(before_matrices[(profile, submode)])
        expected[20:24] = bytes.fromhex(action)
        assert fw.matrices[(profile, submode)] == bytes(expected)
    for submode in range(count, 4):
        assert fw.matrices[(profile, submode)] == before_matrices[(profile, submode)]
    for key, value in before_matrices.items():
        if key[0] != profile:
            assert fw.matrices[key] == value
    assert (
        fw.fields[7][5] & 0x7F
        == {"normal": 0, "dks": 2, "mt": 3, "tgl_hold": 4, "tgl_dots": 5}[definition["mode"]]
    )
    if definition["mode"] == "dks":
        assert [fw.fields[10][stage * 128 + 5] for stage in range(4)] == definition["trigger_modes"]
        writes = [command for command in fw.sent if command[0] in (0x0A, 0x65)]
        assert [command[0] for command in writes] == [0x0A] * 4 + [0x65, 0x65, 0x65]
        assert [command[6] for command in writes[:4]] == [0, 1, 2, 3]
        assert [command[5] for command in writes[:4]] == [0, 0, 0, 1]
        assert writes[4] == codec.packet([0x65, 7, 0, 5, 0, 0, 0, 0, 2])
        dynamic_raw = 70 if model in (3662, 3727) else 140
        assert writes[5] == codec.packet([0x65, 4, 0, 5, 0, 0, 0, 0, dynamic_raw, 0])
        assert writes[6] == codec.packet([0x65, 8, 0, 5, 1, 0, 0, 0, 1, 2, 3, 4])
    assert fw.fields[0][:10] == before_fields[0][:10]
    assert fw.fields[0][12:] == before_fields[0][12:]


@pytest.mark.parametrize("product,model", [(0x502C, 3727), (0x502E, 3759)])
def test_he_magnetic_mode_rejects_corrupt_readback_without_silent_success(product, model):
    fw = Firmware(model_id=model)
    fw.drop_mode_write = True
    kb = keyboard(fw, product=product)
    kb.identify()
    with pytest.raises(ProtocolError):
        kb.set_magnetic_mode(
            5,
            {
                "mode": "dks",
                "actions": ["00000400", "00000500", "00000600", "00000700"],
                "dynamic_travel": 0.7,
                "trigger_modes": [1, 2, 3, 4],
            },
        )


def test_he_magnetic_mode_rejects_unknown_existing_mode_before_writes():
    fw = Firmware()
    modes = bytearray(fw.fields[7])
    modes[5] = 0x66
    fw.fields[7] = bytes(modes)
    kb = keyboard(fw)
    kb.identify()
    sent = len(fw.sent)
    with pytest.raises(ValueError):
        kb.set_magnetic_mode(5, {"mode": "tgl_hold", "actions": ["00000400"]})
    assert len(fw.sent) == sent


def test_he_magnetic_mode_neighbor_corruption_is_reported():
    fw = Firmware()
    fw.corrupt_mode_neighbor = True
    kb = keyboard(fw)
    kb.identify()
    with pytest.raises(ProtocolError):
        kb.set_magnetic_mode(
            5,
            {
                "mode": "dks",
                "actions": ["00000400", "00000500", "00000600", "00000700"],
                "dynamic_travel": 0.7,
                "trigger_modes": [1, 2, 3, 4],
            },
        )


def test_he_magnetic_mode_action_matrix_corruption_is_reported():
    fw = Firmware()
    fw.corrupt_action_after_write = True
    kb = keyboard(fw)
    kb.identify()
    with pytest.raises(ProtocolError):
        kb.set_magnetic_mode(5, {"mode": "tgl_hold", "actions": ["00000400"]})


def test_he_magnetic_mode_noop_does_not_send():
    fw = Firmware()
    kb = keyboard(fw)
    kb.identify()
    definition = {"mode": "tgl_hold", "actions": ["00000400"]}
    kb.set_magnetic_mode(5, definition)
    sent = len(fw.sent)
    result = kb.set_magnetic_mode(5, definition)
    assert result["changed"] is False
    assert len(fw.sent) == sent


def test_he_magnetic_mode_mt_wire_value_is_quantized_on_readback():
    fw = Firmware()
    kb = keyboard(fw)
    kb.identify()
    result = kb.set_magnetic_mode(
        5,
        {"mode": "mt", "actions": ["00000400", "00000500"], "mt_time": 201},
    )
    assert result["changed"] is True
    assert fw.fields[5][5] == 20


def test_he_magnetic_mode_enables_rapid_trigger_and_reads_back_values():
    fw = Firmware()
    for field, raw in ((2, 20), (3, 30)):
        data = bytearray(fw.fields[field])
        data[5 * 2 : 5 * 2 + 2] = raw.to_bytes(2, "little")
        fw.fields[field] = bytes(data)
    kb = keyboard(fw)
    kb.identify()
    result = kb.set_magnetic_mode(
        5,
        {
            "mode": "normal",
            "actions": ["00000400"],
            "travel": 2,
            "lift": 2.8,
            "deadzone": 0.3,
            "fire": True,
        },
    )
    assert result["changed"] is True
    assert fw.fields[7][5] & 0x80
    assert int.from_bytes(fw.fields[2][10:12], "little") == 20
    assert int.from_bytes(fw.fields[3][10:12], "little") == 30


@pytest.mark.parametrize("product,model", [(0x502C, 3727), (0x502E, 3759)])
def test_he_magnetic_mode_cli_uses_real_usb_backend(product, model, tmp_path, monkeypatch, capsys):
    fw = Firmware(model_id=model)
    transport = keyboard(fw, product=product).transport
    info = DeviceInfo(
        "/dev/he-mode-usb",
        "HE60 Lite",
        3,
        0x3151,
        product,
        bytes.fromhex("06ffff0902a10175089540b102c0"),
        "usb",
        0,
    )
    definition = {
        "mode": "tgl_hold",
        "actions": ["00000400"],
    }
    path = tmp_path / "mode.json"
    path.write_text(json.dumps(definition))
    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: transport)
    assert cli.main(["--device", info.path, "magnetic-mode", "5", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["changed"] is True
    assert fw.fields[7][5] & 0x7F == 4


def test_he_magnetic_mode_active_profile_change_is_reported():
    fw = Firmware()
    fw.change_profile_on_read = True
    kb = keyboard(fw)
    with pytest.raises(ProtocolError):
        kb.set_magnetic_mode(5, {"mode": "tgl_hold", "actions": ["00000400"]})


def test_he_magnetic_mode_profile_change_before_write_is_reported():
    fw = Firmware()
    fw.change_profile_on_read = True
    fw.change_profile_on_query = 2
    kb = keyboard(fw)
    with pytest.raises(ProtocolError, match="before magnetic mode write"):
        kb.set_magnetic_mode(5, {"mode": "tgl_hold", "actions": ["00000400"]})
    assert not any(command[0] in (0x0A, 0x65) for command in fw.sent)


def test_he_magnetic_mode_profile_change_after_write_is_reported():
    fw = Firmware()
    fw.change_profile_on_read = True
    fw.change_profile_on_query = 3
    kb = keyboard(fw)
    with pytest.raises(ProtocolError, match="during magnetic mode write"):
        kb.set_magnetic_mode(5, {"mode": "tgl_hold", "actions": ["00000400"]})
    assert any(command[0] in (0x0A, 0x65) for command in fw.sent)


def test_he_wireless_status_reads_rf_version():
    kb = keyboard(Firmware(model_id=3759), product=0x502E)
    status = kb.status()
    assert status["versions"]["rf"] == 0x0500
    assert "magnetic-read" in status["capabilities"]


def test_he_options_and_auto_os_preserve_raw_bytes():
    fw = Firmware()
    fw.options[3] = 0xA5
    fw.options[4] = 0x5A
    kb = keyboard(fw)
    kb.identify()
    assert kb.get_options()["raw"][3:5] == [0xA5, 0x5A]
    result = kb.set_options(system="mac", wasd_swap=True)
    assert result["system"] == "mac" and result["wasd_swap"] is True
    assert result["raw"][3:5] == [0xA5, 0x5A]
    kb.set_auto_os(True)
    assert kb.get_auto_os() is True


def test_he_product_control_gates_and_readbacks():
    fw = Firmware()
    wired = keyboard(fw)
    wired.identify()
    wired.set_debounce(7)
    assert fw.debounce == 7
    with pytest.raises(UnsupportedDevice):
        wired.get_sleep()
    with pytest.raises(UnsupportedDevice):
        wired.set_sleep(60, 60, 60)
    wireless = keyboard(Firmware(model_id=3759), product=0x502E)
    wireless.identify()
    assert wireless.get_sleep() == {
        "bluetooth": 60,
        "dongle": 60,
        "deep_bluetooth": 60,
    }
    assert wireless.set_sleep(120, 180, 240) == {
        "bluetooth": 120,
        "dongle": 180,
        "deep_bluetooth": 240,
    }
    with pytest.raises(ValueError):
        wireless.set_sleep(60, 60, 60, 60)
    with pytest.raises(UnsupportedDevice):
        wireless.set_debounce(7)
    with pytest.raises(UnsupportedDevice):
        wireless._query(codec.packet([0x86]), expected=0x86)
    with pytest.raises(UnsupportedDevice):
        wired._query(codec.packet([0x91]), expected=0x91)
    for invalid in (0, 11, True):
        with pytest.raises(ValueError):
            wired.set_debounce(invalid)


@pytest.mark.parametrize("product,model", [(0x502C, 3727), (0x502E, 3759)])
def test_he_picture_write_and_key_write_use_usb(product, model):
    fw = Firmware(model_id=model)
    kb = keyboard(fw, product=product)
    kb.identify()
    colors = bytes((index * 3) & 255 for index in range(378))
    assert kb.write_picture(colors, picture=0) is None
    assert kb.read_picture(0) == colors
    kb.set_picture_key(0, 2, 0x112233)
    assert kb.read_picture(0)[6:9] == bytes.fromhex("112233")


@pytest.mark.parametrize("values", [(59, 60, 60), (60, 3601, 60), (60, 60, 3601)])
def test_wireless_sleep_bounds(values):
    kb = keyboard(Firmware(model_id=3759), product=0x502E)
    kb.identify()
    with pytest.raises(ValueError):
        kb.set_sleep(*values)


def test_wireless_sleep_write_and_hidden_word_failures():
    dropped = Firmware(model_id=3759)
    dropped.drop_sleep_write = True
    kb = keyboard(dropped, product=0x502E)
    kb.identify()
    with pytest.raises(ProtocolError, match="sleep readback"):
        kb.set_sleep(120, 180, 240)
    corrupt = Firmware(model_id=3759)
    corrupt.corrupt_sleep_hidden = True
    kb = keyboard(corrupt, product=0x502E)
    kb.identify()
    with pytest.raises(ProtocolError, match="hidden sleep"):
        kb.set_sleep(120, 180, 240)


@pytest.mark.parametrize("product,model", [(0x502C, 3727), (0x502E, 3759)])
def test_he_cli_controls_use_real_backend_and_usb(tmp_path, monkeypatch, capsys, product, model):
    from epomaker_driver import cli
    from epomaker_driver.discovery import DeviceInfo

    fw = Firmware(model_id=model)
    original = keyboard(fw, product=product).transport
    info = DeviceInfo("/dev/he-cli", "HE60 Lite", 3, 0x3151, product, b"", "usb", 0)

    class Opened:
        def __enter__(self):
            return original

        def __exit__(self, *_):
            return None

    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: Opened())
    assert cli.main(["--device", info.path, "options", "--system", "mac", "--wasd-swap"]) == 0
    capsys.readouterr()
    assert cli.main(["--device", info.path, "auto-os", "on"]) == 0
    capsys.readouterr()
    assert cli.main(["--device", info.path, "get-light"]) == 0
    capsys.readouterr()
    colors = {"colors": ["112233"] * 126}
    path = tmp_path / "picture.json"
    path.write_text(json.dumps(colors))
    assert cli.main(["--device", info.path, "picture", "0", str(path), "--activate"]) == 0
    capsys.readouterr()
    assert cli.main(["--device", info.path, "picture-key", "0", "2", "#445566"]) == 0
    capsys.readouterr()
    if model == 3727:
        assert cli.main(["--device", info.path, "debounce", "7"]) == 0
    else:
        assert cli.main(["--device", info.path, "sleep", "120", "180", "240"]) == 0
    capsys.readouterr()
    assert fw.options[1] == 1 and fw.options[5] == 1
    assert fw.auto_os is True
    assert fw.light[1] == codec.LIGHT_MODES["picture"]
    expected = bytearray(bytes.fromhex("112233") * 126)
    expected[6:9] = bytes.fromhex("445566")
    assert fw.pictures[0][:378] == expected
    if model == 3727:
        assert fw.debounce == 7
    else:
        assert fw.sleep == [120, 180, 240, 65535]
    assert cli.main(["--device", info.path, "light", "wave", "--speed", "2"]) == 0
    assert fw.light[1:3] == bytes([codec.LIGHT_MODES["wave"], 2])
    capsys.readouterr()


@pytest.mark.parametrize("setting", ["options", "auto_os", "debounce"])
def test_he_common_control_lost_writes(setting):
    fw = Firmware()
    kb = keyboard(fw)
    kb.identify()
    fw.send = lambda command: None
    action = {
        "options": lambda: kb.set_options(system="mac"),
        "auto_os": lambda: kb.set_auto_os(True),
        "debounce": lambda: kb.set_debounce(5),
    }[setting]
    with pytest.raises(ProtocolError, match="readback differs"):
        action()


def test_he_matrix_short_exchange_is_checked_by_backend():
    kb = keyboard(Firmware())
    kb.identify()
    kb.transport.exchange = lambda command, **kwargs: bytes(63)
    with pytest.raises(ProtocolError, match="incomplete HE60 matrix page"):
        kb.read_matrix()


def test_he_supported_identity_guard_rejects_cached_tamper():
    kb = keyboard(Firmware())
    kb.identify()
    kb.identity["device_id"] = 3759
    with pytest.raises(UnsupportedDevice):
        kb.read_matrix()


def test_he_magnetic_no_optional_fields_on_old_firmware():
    fw = Firmware()
    fw.usb_version = 0x0200
    fw.fields[7] = bytes(128)
    value = keyboard(fw).get_magnetic()
    assert "251" not in value["fields"]


@pytest.mark.parametrize("model,boot", [(3727, True), (3759, False)])
def test_he_rejects_boot_or_product_id_mismatch(model, boot):
    with pytest.raises(UnsupportedDevice):
        keyboard(Firmware(model_id=model, boot=boot), product=0x502C).identify()


@pytest.mark.parametrize(
    ("usb", "rf", "multiplier", "top"),
    [
        (0, 0, 10, False),
        (0x2FF, 0, 10, False),
        (0x300, 0, 100, False),
        (0x500, 0, 200, True),
        (0x500, 0x200, 10, True),
        (0x200, 0x400, 100, True),
    ],
)
def test_he_version_scaling_and_raw_page_preservation(usb, rf, multiplier, top):
    fw = Firmware(model_id=3759)
    fw.usb_version, fw.rf_version = usb, rf
    fw.fields[7] = b"\x66" + bytes(127)
    fw.fields[0] = b"\x96\x00" + bytes(254)
    fw.fields[251] = b"\x96" + bytes(127)
    result = keyboard(fw, product=0x502E).get_magnetic()
    assert result["versions"] == {"usb": usb or None, "rf": rf or None}
    assert result["multiplier"] == multiplier
    assert result["slots"][0]["travel"] == 150 / multiplier
    assert result["slots"][0]["mode"] is None
    assert result["slots"][0]["raw_mode"] == 0x66
    expected_fields = {"7", "0", "1", "6"} | ({"251"} if top else set())
    assert set(result["fields"]) == expected_fields
    for field in expected_fields:
        length = 128 if field in ("7", "251") else 256
        assert result["fields"][field] == fw.fields[int(field)][:length].hex()
        assert [c[3] for c in fw.query_log if c[0] == 0xE5 and c[1] == int(field)] == list(
            range(length // 64)
        )
    if top:
        assert result["slots"][0]["top_deadzone"] == 150 / multiplier


@pytest.mark.parametrize(("model", "product"), [(3727, 0x502C), (3759, 0x502E)])
def test_he_cli_through_usb(monkeypatch, capsys, model, product):
    fw = Firmware(model_id=model)
    info = DeviceInfo(
        "/dev/hidraw60",
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
    prefix = ["--device", info.path]
    assert cli.main([*prefix, "key", "9", "00000500", "--profile", "1", "--submode", "3"]) == 0
    capsys.readouterr()
    assert cli.main([*prefix, "matrix", "--profile", "1", "--submode", "3"]) == 0
    assert json.loads(capsys.readouterr().out)["slots"][9] == [0, 0, 5, 0]
    assert cli.main([*prefix, "get-magnetic"]) == 0
    assert len(json.loads(capsys.readouterr().out)["slots"]) == 128


@pytest.mark.parametrize(("model", "product"), [(3727, 0x502C), (3759, 0x502E)])
def test_he_actuation_write_preserves_other_slots(model, product):
    fw = Firmware(model_id=model)
    # Both fixtures support top dead zone, with scales 100 and 200 respectively.
    before = fw.fields.copy()
    kb = keyboard(fw, product=product)
    result = kb.set_magnetic(1, {"travel": 1.2, "deadzone": 0.3, "top_deadzone": 0.4})
    assert result["changed"]
    assert result["slot"]["travel"] == 1.2
    assert result["slot"]["deadzone"] == 0.3
    assert result["slot"]["top_deadzone"] == 0.4
    multiplier = 100 if model == 3727 else 200
    for field, value, width in (
        (0, 12 * multiplier // 10, 2),
        (6, 3 * multiplier // 10, 2),
        (251, 4 * multiplier // 10, 1),
    ):
        expected = bytearray(before[field])
        expected[width : 2 * width] = value.to_bytes(width, "little")
        before[field] = bytes(expected)
    assert fw.fields == before
    writes = [command for command in fw.sent if command[0] == 0x65]
    assert [command[1] for command in writes] == [0, 6, 251]
    assert [command[4] for command in writes] == [0, 0, 1]
    sent = len(fw.sent)
    assert not kb.set_magnetic(1, {"travel": 1.2})["changed"]
    assert len(fw.sent) == sent


def test_he_enable_and_disable_rapid_trigger_preserves_thresholds():
    fw = Firmware(model_id=3759)
    kb = keyboard(fw, product=0x502E)
    result = kb.set_magnetic(1, {"fire": True, "rapid_press": 0.2, "rapid_lift": 0.3})
    assert result["slot"]["raw_mode"] == 0x80
    assert result["slot"]["rapid_press"] == 0.2
    assert result["slot"]["rapid_lift"] == 0.3
    writes = [command for command in fw.sent if command[0] == 0x65]
    assert [command[1] for command in writes] == [7, 2, 3]
    assert [command[4] for command in writes] == [0, 0, 1]
    before = fw.fields.copy()
    result = kb.set_magnetic(1, {"fire": False})
    assert not result["slot"]["fire"]
    assert fw.fields[2] == before[2] and fw.fields[3] == before[3]


@pytest.mark.parametrize("flag", ["drop_magnetic_write", "corrupt_magnetic_neighbor"])
def test_he_magnetic_readback_detects_lost_or_unrelated_writes(flag):
    fw = Firmware()
    setattr(fw, flag, True)
    with pytest.raises(ProtocolError, match="readback differs"):
        keyboard(fw).set_magnetic(1, {"travel": 1.2})


@pytest.mark.parametrize(
    "patch",
    [
        {"travel": -1},
        {"travel": 1.25},
        {"fire": False, "rapid_press": 0.2},
        {"top_deadzone": 2},
        {},
    ],
)
def test_he_invalid_magnetic_patch_never_writes(patch):
    fw = Firmware()
    with pytest.raises(ValueError):
        keyboard(fw).set_magnetic(1, patch)
    assert not fw.sent


def test_he_cli_magnetic_write(monkeypatch, capsys):
    fw = Firmware(model_id=3759)
    info = DeviceInfo(
        "/dev/hidraw60",
        "HE60 Lite",
        3,
        0x3151,
        0x502E,
        bytes.fromhex("06ffff0902a10175089540b102c0"),
        "usb",
        0,
    )
    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: keyboard(fw, product=0x502E).transport)
    assert (
        cli.main(
            [
                "--device",
                info.path,
                "magnetic-key",
                "1",
                "--fire",
                "--rapid-press",
                "0.2",
                "--rapid-lift",
                "0.2",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["changed"] and result["slot"]["fire"]
    sent = len(fw.sent)
    assert cli.main(["--device", info.path, "magnetic-key", "1"]) == 1
    assert "choose at least one" in capsys.readouterr().err
    assert len(fw.sent) == sent


@pytest.mark.parametrize("change_at", [3, 4])
def test_he_magnetic_profile_race_before_or_after_write(monkeypatch, change_at):
    fw = Firmware()
    exchange = fw.exchange
    count = 0

    def raced(command):
        nonlocal count
        if command[0] == 0x84:
            count += 1
            if count == change_at:
                fw.profile = 1
        return exchange(command)

    monkeypatch.setattr(fw, "exchange", raced)
    with pytest.raises(ProtocolError, match="profile changed"):
        keyboard(fw).set_magnetic(1, {"travel": 1.2})
    assert bool(fw.sent) is (change_at == 4)


def test_he_inactive_rapid_fields_are_read_only_when_needed():
    fw = Firmware(model_id=3759)
    fw.fields[7] = bytes(128)
    fw.fields[2] = b"\x28\x00" * 128  # 0.2 mm at scale 200.
    fw.fields[3] = b"\x3c\x00" * 128  # 0.3 mm at scale 200.
    kb = keyboard(fw, product=0x502E)
    kb.set_magnetic(1, {"travel": 1.2})
    assert not any(c[0] == 0xE5 and c[1] in (2, 3) for c in fw.query_log)
    fw.query_log.clear()
    result = kb.set_magnetic(1, {"fire": True})
    assert result["slot"]["rapid_press"] == 0.2
    assert result["slot"]["rapid_lift"] == 0.3
    assert [c[1] for c in fw.sent if c[0] == 0x65][-1] == 7
    for field in (2, 3):
        assert [c[3] for c in fw.query_log if c[0] == 0xE5 and c[1] == field] == list(range(4)) * 2


def test_he_magnetic_send_failure_stops_sequence(monkeypatch):
    fw = Firmware()
    original_send = fw.send
    count = 0

    def fail_second(command):
        nonlocal count
        if command[0] == 0x65:
            count += 1
            if count == 2:
                raise OSError("simulated failure")
        original_send(command)

    monkeypatch.setattr(fw, "send", fail_second)
    with pytest.raises(OSError, match="simulated failure"):
        keyboard(fw).set_magnetic(1, {"travel": 1.2, "deadzone": 0.3, "top_deadzone": 0.4})
    assert count == 2
    assert [c[1] for c in fw.sent if c[0] == 0x65] == [0]


def test_mode_invalid_preserved_rapid_thresholds_require_explicit_repair():
    fw = Firmware()
    # Slot zero starts with fire enabled and out-of-range fixture thresholds.
    kb = keyboard(fw)
    definition = {"mode": "tgl_hold", "actions": ["00000400"]}
    with pytest.raises(ValueError, match="provide valid rapid_press"):
        kb.set_magnetic_mode(0, definition)
    assert not fw.sent
    result = kb.set_magnetic_mode(0, {**definition, "rapid_press": 0.2, "rapid_lift": 0.3})
    assert result["changed"]
    assert fw.fields[7][0] == 0x84
    assert fw.fields[2][:2] == bytes([20, 0])
    assert fw.fields[3][:2] == bytes([30, 0])
