import json

import pytest

from epomaker_driver import cli
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
        self.macros = {slot: bytes(256) for slot in range(256)}
        self.matrices = {
            (profile, mode): bytes([profile, mode]) * 256
            for profile in range(2)
            for mode in range(4)
        }
        self.fn = {(layer, os): bytes([layer, os]) * 256 for layer in range(2) for os in range(2)}
        self.fields = {
            field: bytes([field]) * 256 for field in (0, 1, 2, 3, 4, 5, 6, 7, 9, 251, 252)
        }
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
            if self.change_profile_on_read:
                self.profile = 1 - self.profile
            return bytes(raw)
        if op == 0x8A:
            data = self.matrices[(command[1], command[4])]
            result = data[command[3] * 64 : (command[3] + 1) * 64]
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
        self.sent.append(command)
        if command[0] == 0x04:
            self.profile = command[1]
        elif command[0] == 0x0A:
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

        def get_feature(self, *_):
            assert _ == (0, 64)
            response = getattr(self, "response", bytes(64))
            if not firmware.short_pages:
                assert len(response) == 64
            return response

        def close(self):
            pass

    return HEKeyboard(Transport(USB(), "usb", sleep=lambda _: None), product_id=product)


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


def test_he_wireless_status_reads_rf_version():
    kb = keyboard(Firmware(model_id=3759), product=0x502E)
    status = kb.status()
    assert status["versions"]["rf"] == 0x0500
    assert "magnetic-read" in status["capabilities"]


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
