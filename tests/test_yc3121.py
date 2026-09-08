"""YC3121 wire fixtures on a USB feature-report simulator; no vendor code loaded."""

import json

import pytest

from epomaker_driver import cli, codec
from epomaker_driver.discovery import DeviceInfo, classify, parse_descriptor
from epomaker_driver.errors import ProtocolError, UnsupportedDevice
from epomaker_driver.legacy import LegacyKeyboard
from epomaker_driver.transport import Transport


class Firmware:
    def __init__(self, model):
        self.model = model
        self.version = 0x213
        self.profile = 0
        self.matrices = [bytearray(bytes(range(256)) * 2) for _ in range(3)]
        self.macros = [bytearray(256) for _ in range(256)]
        self.macro_pending = bytearray(280)
        self.timers = bytes.fromhex("7800f0000807100e")
        self.debounce = 10
        self.picture = bytearray(384)
        self.light = bytearray(64)
        self.light[:8] = bytes.fromhex("8701050407123456")
        self.auto_os = False
        self.commands = []
        self.response = bytes(64)
        self.closed = False
        self.ignore_writes = False
        self.short_reply = False

    def set_feature(self, report):
        assert len(report) == 65 and report[0] == 0
        p = report[1:]
        assert sum(p[:9] if p[0] == 7 else p[:8]) % 256 == 255
        self.commands.append(p)
        op = p[0]
        raw = bytearray(64)
        raw[0] = op
        if op == 0x8F:
            raw[1:5] = self.model.to_bytes(4, "little")
        elif op == 0x80:
            raw[1:3] = self.version.to_bytes(2, "little")
        elif op == 0x85:
            raw[1] = self.profile
        elif op == 0x89:
            assert p[3:7] == bytes(4)
            raw[:] = self.matrices[p[1]][p[2] * 64 : (p[2] + 1) * 64]
        elif op == 0x8B:
            assert p[3:7] == bytes(4)
            raw[:] = self.macros[p[1]][p[2] * 64 : (p[2] + 1) * 64]
        elif op == 0x8C:
            assert p[1] == 0 and p[3:7] == bytes(4)
            raw[:] = self.picture[p[2] * 64 : (p[2] + 1) * 64]
        elif op == 0x87:
            raw[:] = self.light
        elif op == 0x92:
            raw[1:9] = self.timers
        elif op == 0x91:
            raw[2] = self.debounce
        elif op == 0x97:
            raw[1] = int(self.auto_os)
        elif not self.ignore_writes:
            if op == 5:
                self.profile = p[1]
            elif op == 0x13:
                assert p[3:7] == bytes(4) and p[12:] == bytes(52)
                self.matrices[p[1]][p[2] * 4 : p[2] * 4 + 4] = p[8:12]
            elif op == 0x16:
                assert p[3] == 56 and p[5:7] == bytes(2)
                self.macro_pending[p[2] * 56 : (p[2] + 1) * 56] = p[8:64]
                if p[4] == 1:
                    self.macros[p[1]][:] = self.macro_pending[:256]
            elif op == 0x0C:
                assert p[1:4] == bytes([0, 128, 1]) and p[5:7] == bytes(2)
                start = p[4] * 56
                size = min(56, 384 - start)
                self.picture[start : start + size] = p[8 : 8 + size]
            elif op == 7:
                self.light[:] = p
                self.light[0] = 0x87
            elif op == 0x12:
                self.timers = p[8:16]
            elif op == 0x11:
                assert p[1] == 0
                self.debounce = p[2]
            elif op == 0x17:
                self.auto_os = bool(p[1])
            else:
                pytest.fail(f"unimplemented opcode {op:02x}")
        self.response = bytes(raw)

    def get_feature(self, report_id, length):
        assert (report_id, length) == (0, 64)
        return self.response[:-1] if self.short_reply else self.response

    def close(self):
        self.closed = True


@pytest.fixture(params=[1379, 1723])
def legacy(request):
    firmware = Firmware(request.param)
    transport = Transport(firmware, "usb", sleep=lambda _: None)
    return LegacyKeyboard(transport), firmware


def test_core_roundtrip(legacy):
    keyboard, fw = legacy
    status = keyboard.status()
    assert status["identity"] == {"device_id": fw.model, "usb_version": 0x213, "is_boot": None}
    assert status["capabilities"] == [
        "keymap",
        "profile",
        "sleep",
        "debounce",
        "auto-os",
        "macro",
        "lighting",
    ]
    assert status["profiles"] == 3 and status["profile"] == 0
    assert status["sleep"]["bluetooth"] == 120
    keyboard.set_profile(2)
    assert keyboard.get_profile() == 2
    before = keyboard.read_matrix()
    assert keyboard.set_key(127, [0, 0, 4, 0], profile=2) == [0, 0, 4, 0]
    assert keyboard.read_matrix(2)[508:] == bytes([0, 0, 4, 0])
    assert keyboard.read_matrix() == before
    # Preserve all opaque bytes, including both slots omitted by the vendor bulk writer.
    desired = bytearray(keyboard.read_matrix(2))
    desired[504:] = b"\x05\x06\x07\x08\x09\x0a\x0b\x0c"
    fw.commands.clear()
    keyboard.write_matrix(desired, 2)
    assert [p[2] for p in fw.commands if p[0] == 0x13] == [126, 127]
    fw.commands.clear()
    keyboard.write_matrix(desired, 2)
    assert not any(p[0] < 128 for p in fw.commands)
    keyboard.set_sleep(60, 3600, 600, 3600)
    assert keyboard.get_sleep() == dict(
        bluetooth=60, dongle=3600, deep_bluetooth=600, deep_dongle=3600
    )
    keyboard.set_debounce(255)
    assert keyboard.get_debounce() == 255
    keyboard.set_auto_os(True)
    assert keyboard.get_auto_os()
    keyboard.set_auto_os(False)
    assert not keyboard.get_auto_os()


@pytest.mark.parametrize(
    "operation",
    [
        lambda k: k.set_profile(3),
        lambda k: k.read_matrix(-1),
        lambda k: k.set_key(128, bytes(4)),
        lambda k: k.set_key(0, bytes(3)),
        lambda k: k.set_key(0, bytes(4), fn=True),
        lambda k: k.read_matrix(fn=True),
        lambda k: k.read_matrix(os_mode=1),
        lambda k: k.write_matrix(bytes(504)),
        lambda k: k.set_sleep(59, 60, 600, 600),
        lambda k: k.set_sleep(60, 60, 600),
        lambda k: k.set_sleep(60, 60, 600, 3601),
        lambda k: k.set_debounce(256),
        lambda k: k.set_auto_os(1),
    ],
)
def test_invalid_input_never_writes(legacy, operation):
    keyboard, fw = legacy
    with pytest.raises((ValueError, UnsupportedDevice)):
        operation(keyboard)
    assert not any(p[0] < 128 for p in fw.commands)


@pytest.mark.parametrize(
    "operation",
    [
        lambda k: k.set_profile(2),
        lambda k: k.set_key(0, bytes(4)),
        lambda k: k.write_matrix(bytes(512)),
        lambda k: k.set_sleep(60, 60, 600, 600),
        lambda k: k.set_debounce(255),
        lambda k: k.set_auto_os(True),
    ],
)
def test_write_readback_failures(legacy, operation):
    keyboard, fw = legacy
    fw.ignore_writes = True
    with pytest.raises(ProtocolError, match="readback differs"):
        operation(keyboard)


def test_identity_gates_and_invalidation(legacy):
    keyboard, fw = legacy
    keyboard.identify()
    fw.model = 1955  # magnetic profile addressing is not silently treated as the normal family
    with pytest.raises(UnsupportedDevice):
        keyboard.identify()
    assert keyboard.identity is None and keyboard.model is None
    fw.model = 1379
    fw.version = 0
    with pytest.raises(ProtocolError, match="normal firmware"):
        keyboard.set_key(0, bytes(4))
    assert not any(p[0] < 128 for p in fw.commands)


def test_invalid_profile_response(legacy):
    keyboard, fw = legacy
    fw.profile = 3
    with pytest.raises(ProtocolError, match="invalid profile"):
        keyboard.get_profile()


@pytest.mark.parametrize("method", ["identify", "get_sleep", "read_matrix"])
def test_short_responses(legacy, method):
    keyboard, fw = legacy
    keyboard.identify()
    fw.short_reply = True
    with pytest.raises(ProtocolError):
        getattr(keyboard, method)()


def test_descriptor_and_cli(legacy, monkeypatch, capsys):
    keyboard, fw = legacy
    descriptor = bytes.fromhex("06ffff0902a10175089540b102c0")
    assert classify(3, 0x3151, 0x4015, parse_descriptor(descriptor)) == ("usb", 0)
    assert classify(5, 0x3151, 0x4015, parse_descriptor(descriptor)) == (None, None)
    info = DeviceInfo("/dev/hidraw99", "YC3121", 3, 0x3151, 0x4015, descriptor, "usb", 0)
    monkeypatch.setattr(cli, "discover", lambda: [info])
    # Each invocation opens its own transport, as the real CLI does.
    monkeypatch.setattr(cli.Transport, "open", lambda _: Transport(fw, "usb", sleep=lambda _: None))
    prefix = ["--device", info.path]
    for command in (
        ["status"],
        ["get-light"],
        ["light", "wave", "--speed", "4", "--option", "3"],
        ["matrix", "--decoded"],
        ["bind-key", "3", "a"],
        ["profile", "2"],
        ["sleep", "60", "120", "600", "1200"],
        ["auto-os", "on"],
        ["debounce", "20"],
    ):
        assert cli.main([*prefix, *command]) == 0
        assert json.loads(capsys.readouterr().out) is not None
    fw.commands.clear()
    assert cli.main([*prefix, "clock"]) == 1
    assert "not been migrated" in capsys.readouterr().err
    assert fw.commands == []
    assert fw.closed


def test_direct_usb_required():
    with pytest.raises(UnsupportedDevice, match="direct USB"):
        LegacyKeyboard(Transport(Firmware(1379), "bluetooth", sleep=lambda _: None))


@pytest.mark.parametrize(
    "opcode,operation",
    [
        (0x8F, "identify"),
        (0x80, "identify"),
        (0x92, "get_sleep"),
        (0x89, "read_matrix"),
    ],
)
def test_protocol_boundary_rejects_partial_custom_transport(legacy, monkeypatch, opcode, operation):
    keyboard, fw = legacy
    # Exercise the device boundary independently of Linux transport's own length guard.
    exchange = keyboard.transport.exchange

    def truncated(command, **kwargs):
        reply = exchange(command, **kwargs)
        return reply[:4] if command[0] == opcode else reply

    monkeypatch.setattr(keyboard.transport, "exchange", truncated)
    with pytest.raises(ProtocolError):
        getattr(keyboard, operation)()
    assert not any(p[0] < 128 for p in fw.commands)


@pytest.mark.parametrize("slot", [0, 255])
def test_macro_sparse_clear_and_slot_isolation(legacy, slot):
    keyboard, fw = legacy
    other = 255 - slot
    fw.macros[other][:] = bytes([77]) * 256
    for desired in (bytes(range(256)), bytes(254) + b"\x12\x34", b"\x01" + bytes(255), bytes(256)):
        fw.commands.clear()
        keyboard.write_macro(slot, desired)
        assert keyboard.read_macro(slot) == desired
        assert fw.macros[other] == bytes([77]) * 256
        writes = [p for p in fw.commands if p[0] < 128]
        assert len(writes) == 5
        assert [p[2] for p in writes] == [0, 1, 2, 3, 4]
        assert [p[4] for p in writes] == [0, 0, 0, 0, 1]
        assert writes[-1][40:] == bytes(24)
        assert b"".join(p[8:] for p in writes)[:256] == desired


@pytest.mark.parametrize(
    "slot,data",
    [(-1, bytes(256)), (256, bytes(256)), (True, bytes(256)), (0, bytes(255)), (0, bytes(257))],
)
def test_invalid_macro_never_sends(legacy, slot, data):
    keyboard, fw = legacy
    with pytest.raises(ValueError):
        keyboard.write_macro(slot, data)
    assert fw.commands == []


def test_macro_readback_failure_and_bad_slot(legacy):
    keyboard, fw = legacy
    with pytest.raises(ValueError):
        keyboard.read_macro(256)
    assert fw.commands == []
    fw.ignore_writes = True
    with pytest.raises(ProtocolError, match="macro readback differs"):
        keyboard.write_macro(0, bytes([9]) * 256)


def test_macro_partial_read_custom_transport(legacy, monkeypatch):
    keyboard, fw = legacy
    exchange = keyboard.transport.exchange

    def partial(command, **kwargs):
        data = exchange(command, **kwargs)
        return data[:12] if command[0] == 0x8B and command[2] == 2 else data

    monkeypatch.setattr(keyboard.transport, "exchange", partial)
    with pytest.raises(ProtocolError, match="macro page 2"):
        keyboard.read_macro(0)


def test_macro_cli(legacy, monkeypatch, tmp_path, capsys):
    keyboard, fw = legacy
    info = DeviceInfo("/dev/hidraw99", "YC3121", 3, 0x3151, 0x4015, b"", "usb", 0)
    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: Transport(fw, "usb", sleep=lambda _: None))
    path = tmp_path / "macro.json"
    events = [
        {"hid_usage": 4, "down": True, "delay_ms": 10},
        {"hid_usage": 4, "down": False, "delay_ms": 300},
    ]
    path.write_text(json.dumps({"repeat": 1, "events": events}))
    prefix = ["--device", info.path]
    assert cli.main([*prefix, "macro", "7", str(path)]) == 0
    capsys.readouterr()
    assert cli.main([*prefix, "get-macro", "7", "--decoded"]) == 0
    assert json.loads(capsys.readouterr().out)["repeat"] == 1
    assert cli.main([*prefix, "bind-macro", "9", "7"]) == 0
    capsys.readouterr()
    assert fw.matrices[0][36:40] != bytes(4)


@pytest.mark.parametrize("mode", [mode for mode in codec.LIGHT_MODES if mode != "off"])
@pytest.mark.parametrize("rainbow", [False, True])
def test_lighting_modes(legacy, mode, rainbow):
    keyboard, fw = legacy
    speed = 0 if mode in ("solid", "picture", "music", "screen") else 4
    result = keyboard.set_light(mode, rgb=0xFFFFFF, speed=speed, rainbow=rainbow)
    assert result["mode"] == mode and result["speed"] == speed
    packet = next(p for p in reversed(fw.commands) if p[0] == 7)
    assert packet[2] == 5 - speed
    assert packet[5:8] == (bytes([0, 200, 200]) if mode == "picture" else bytes.fromhex("fafffa"))
    assert packet[4] == (
        0
        if mode in ("picture", "screen")
        else (0 if rainbow else 4)
        if mode == "music"
        else (8 if rainbow else 7)
    )
    assert sum(packet[:9]) % 256 == 255


@pytest.mark.parametrize(
    "mode,options",
    [
        ("off", {}),
        ("solid", {"side": True}),
        ("unknown", {}),
        ("wave", {"speed": 5}),
        ("wave", {"option": 4}),
        ("picture", {"option": 3}),
        ("music", {"option": 3}),
        ("snake", {"option": 2}),
        ("solid", {"speed": 1}),
        ("breathing", {"option": 1}),
    ],
)
def test_lighting_limits_before_writes(legacy, mode, options):
    keyboard, fw = legacy
    with pytest.raises((ValueError, UnsupportedDevice)):
        keyboard.set_light(mode, **options)
    assert fw.commands == []


def test_lighting_readback_and_unknown_values(legacy):
    keyboard, fw = legacy
    with pytest.raises(UnsupportedDevice, match="side-light"):
        keyboard.get_light(side=True)
    assert fw.commands == []
    fw.light[1] = 250
    assert keyboard.get_light()["mode"] == "unknown"
    fw.ignore_writes = True
    with pytest.raises(ProtocolError, match="lighting readback differs"):
        keyboard.set_light("solid")
    fw.ignore_writes = False
    assert keyboard.set_light("picture", option=2)["option"] == 2
    assert keyboard.set_light("wave", option=3, speed=0, brightness=0)["brightness"] == 0


def test_picture_full_length_and_edit(legacy):
    keyboard, fw = legacy
    colors = bytes(range(256)) + bytes(range(128))
    keyboard.write_picture(colors)
    assert keyboard.read_picture() == colors
    writes = [p for p in fw.commands if p[0] == 12]
    assert len(writes) == 7 and writes[-1][-8:] == bytes(8)
    assert [p[4] for p in writes] == list(range(7))
    keyboard.set_picture_key(0, 127, 0xFFFFFF)
    assert keyboard.read_picture() == colors[:-3] + b"\xff\xff\xff"
    keyboard.set_picture_key(0, 0, 0)
    assert keyboard.read_picture()[3:-3] == colors[3:-3]
    keyboard.write_picture(bytes(384))
    assert keyboard.read_picture() == bytes(384)


@pytest.mark.parametrize(
    "operation",
    [
        lambda k: k.read_picture(1),
        lambda k: k.write_picture(bytes(384), 2),
        lambda k: k.write_picture(bytes(378)),
        lambda k: k.set_picture_key(0, 128, 0),
        lambda k: k.set_picture_key(0, 0, 0x1000000),
    ],
)
def test_picture_bounds(legacy, operation):
    keyboard, fw = legacy
    with pytest.raises(ValueError):
        operation(keyboard)
    assert fw.commands == []


def test_picture_readback_failure(legacy, monkeypatch):
    keyboard, fw = legacy
    fw.ignore_writes = True
    with pytest.raises(ProtocolError, match="picture readback differs"):
        keyboard.write_picture(bytes([4]) * 384)
    exchange = keyboard.transport.exchange

    def partial(command, **kwargs):
        data = exchange(command, **kwargs)
        return data[:20] if command[0] == 0x8C else data

    monkeypatch.setattr(keyboard.transport, "exchange", partial)
    with pytest.raises(ProtocolError, match="picture page"):
        keyboard.read_picture()


def test_picture_cli(legacy, monkeypatch, tmp_path, capsys):
    keyboard, fw = legacy
    info = DeviceInfo("/dev/hidraw99", "YC3121", 3, 0x3151, 0x4015, b"", "usb", 0)
    monkeypatch.setattr(cli, "discover", lambda: [info])
    monkeypatch.setattr(cli.Transport, "open", lambda _: Transport(fw, "usb", sleep=lambda _: None))
    path = tmp_path / "picture.json"
    path.write_text(json.dumps({"colors": ["abcdef"] * 128}))
    prefix = ["--device", info.path]
    assert cli.main([*prefix, "picture", "0", str(path), "--activate"]) == 0
    capsys.readouterr()
    assert cli.main([*prefix, "picture-key", "0", "127", "123456"]) == 0
    capsys.readouterr()
    assert cli.main([*prefix, "get-picture", "0"]) == 0
    colors = json.loads(capsys.readouterr().out)["colors"]
    assert len(colors) == 128 and colors[-1] == "123456" and colors[0] == "abcdef"
    assert fw.light[1] == 13 and fw.light[4] == 0
