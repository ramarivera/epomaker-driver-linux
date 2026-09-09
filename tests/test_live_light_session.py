import pytest

from epomaker_driver import codec, server
from epomaker_driver.device import Keyboard
from epomaker_driver.discovery import DeviceInfo
from epomaker_driver.errors import ProtocolError, UnsupportedDevice
from epomaker_driver.live_light_session import LiveLightSession
from epomaker_driver.server import Controller


def advertise_light_sync(firmware, *, boot=False):
    """Advertise the simulator-only 0x8f capability without changing fixtures."""

    exchange = firmware.exchange

    def wrapped(command, **options):
        response = bytearray(exchange(command, **options))
        if command[0] == 0x8F:
            response[11] = 1
            response[9] = int(boot)
        return bytes(response)

    firmware.exchange = wrapped


def keyboard(firmware):
    advertise_light_sync(firmware)
    return Keyboard(firmware)


@pytest.fixture
def controller(tmp_path, firmware, descriptor):
    advertise_light_sync(firmware)
    info = DeviceInfo(
        "/dev/hidraw-test", "Glyph simulator", 5, 0x3151, 0x5004, descriptor, "usb", 6
    )
    return Controller(
        tmp_path / "backups",
        discovery=lambda: [info],
        transport_factory=lambda _info: firmware,
    )


def connect(controller):
    return controller.call("connect", {"path": "/dev/hidraw-test"})


def test_start_requires_glyph_usb_and_firmware_capability(firmware):
    session = LiveLightSession()
    firmware.kind = "bluetooth"
    with pytest.raises(UnsupportedDevice, match="wired USB"):
        session.start(Keyboard(firmware))
    assert session.session is None

    firmware.kind = "usb"
    with pytest.raises(UnsupportedDevice, match="light-sync"):
        session.start(Keyboard(firmware))
    assert session.session is None


def test_start_rejects_boot_identity_without_creating_session(firmware):
    advertise_light_sync(firmware, boot=True)
    with pytest.raises(UnsupportedDevice, match="wired USB"):
        LiveLightSession().start(Keyboard(firmware))


def test_duplicate_start_is_rejected_and_stop_restores_exact_raw_options(firmware):
    original = codec.packet([7, 22, 3, 2, 0xB5, 0x12, 0x34, 0x56], 8)
    firmware.light = bytearray(original)
    kb = keyboard(firmware)
    session = LiveLightSession()

    token = session.start(kb)["session"]
    assert firmware.light[1] == 1  # host-follow effect is paused while streaming
    with pytest.raises(ValueError, match="already running"):
        session.start(kb)

    assert session.stop(token) == {"ok": True}
    assert bytes(firmware.light) == original
    assert session.session is None


@pytest.mark.parametrize("colors", ["", "0" * 754, "0" * 758, "g" * 756, None, 123])
def test_frame_rejects_non_strict_378_byte_hex_without_writing(firmware, colors):
    kb = keyboard(firmware)
    session = LiveLightSession()
    token = session.start(kb)["session"]
    sent = len(firmware.sent)

    with pytest.raises(ValueError, match="378 RGB bytes"):
        session.frame(token, colors)
    assert len(firmware.sent) == sent


def test_stale_frame_and_stop_cannot_affect_replacement(firmware):
    kb = keyboard(firmware)
    session = LiveLightSession()
    old = session.start(kb)["session"]
    session.cancel()
    replacement = session.start(kb)["session"]

    assert old != replacement
    assert session.stop(old) == {"ok": True}
    with pytest.raises(ValueError, match="session ended"):
        session.frame(old, "00" * 378)
    assert session.session == replacement
    session.stop(replacement)


def test_successful_frame_returns_ok_and_stop_restores_saved_state(firmware):
    kb = keyboard(firmware)
    session = LiveLightSession()
    token = session.start(kb)["session"]
    sent = len(firmware.sent)

    assert session.frame(token, "12" * 378) == {"ok": True}
    assert len(firmware.sent) == sent + 7
    assert all(command[0] == 15 for command in firmware.sent[sent:])
    assert session.stop(token) == {"ok": True}


def test_start_set_light_failure_cancels_partial_session(firmware, monkeypatch):
    firmware.light = bytearray(codec.packet([7, 22, 3, 2, 0xB5, 1, 2, 3], 8))
    kb = keyboard(firmware)
    session = LiveLightSession()
    monkeypatch.setattr(
        kb, "set_light", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("pause"))
    )

    with pytest.raises(OSError, match="pause"):
        session.start(kb)
    assert session.session is None
    assert session.keyboard is None and session.saved is None


def test_stop_reports_readback_mismatch_and_invalidates_session(firmware, monkeypatch):
    kb = keyboard(firmware)
    session = LiveLightSession()
    token = session.start(kb)["session"]
    bad = bytearray(codec.packet([0x87, 1, 4, 4, 7, 0, 0, 0], 8))
    monkeypatch.setattr(kb, "get_light", lambda **_kwargs: {"raw": list(bad)})

    with pytest.raises(ProtocolError, match="restoration readback"):
        session.stop(token)
    assert session.session is None


def test_read_light_failure_does_not_leave_active_session(firmware):
    kb = keyboard(firmware)
    original_exchange = firmware.exchange

    def fail_light(command, **options):
        if command[0] == 0x87:
            raise OSError("read failed")
        return original_exchange(command, **options)

    firmware.exchange = fail_light
    with pytest.raises(OSError, match="read failed"):
        LiveLightSession().start(kb)


def test_frame_send_failure_restores_and_cancels_session(firmware, monkeypatch):
    kb = keyboard(firmware)
    session = LiveLightSession()
    token = session.start(kb)["session"]
    original = bytes(firmware.light)

    def fail_send(_colors):
        raise OSError("frame transport failed")

    monkeypatch.setattr(kb, "send_live_colors", fail_send)
    with pytest.raises(OSError, match="frame transport failed"):
        session.frame(token, "00" * 378)
    assert session.session is None
    assert bytes(firmware.light) == original


def test_frame_send_and_restore_failure_reports_both_and_cancels(firmware, monkeypatch):
    kb = keyboard(firmware)
    session = LiveLightSession()
    token = session.start(kb)["session"]

    monkeypatch.setattr(
        kb, "send_live_colors", lambda _colors: (_ for _ in ()).throw(OSError("send"))
    )
    monkeypatch.setattr(kb, "_write", lambda _commands: (_ for _ in ()).throw(OSError("restore")))
    with pytest.raises(ProtocolError, match="could not be restored"):
        session.frame(token, "00" * 378)
    assert session.session is None


def test_stop_with_stale_token_is_a_noop(firmware):
    session = LiveLightSession()
    assert session.stop("missing") == {"ok": True}
    assert session.session is None


def test_controller_disconnect_and_reconnect_invalidate_session(controller):
    connect(controller)
    token = controller.call("live_light_start", {})["session"]
    assert controller.live_light.session == token

    assert controller.call("disconnect", {}) == {"ok": True}
    assert controller.live_light.session is None
    connect(controller)
    assert controller.live_light.session is None


def test_other_write_stops_and_restores_before_writing_new_lighting(controller, firmware):
    connect(controller)
    original = bytes(firmware.light)
    controller.call("live_light_start", {})
    controller.call(
        "write",
        {
            "kind": "lighting",
            "mode": "solid",
            "side": False,
            "rgb": 0x010203,
            "brightness": 3,
            "speed": 2,
        },
    )
    assert controller.live_light.session is None
    writes = [command for command in firmware.sent if command[0] == 7]
    assert bytes(writes[-2]) == original
    assert bytes(firmware.light)[1:8] == bytes((1, 2, 3, 7, 1, 2, 3))


def test_restore_and_factory_reset_invalidate_live_session(controller, monkeypatch):
    connect(controller)
    controller.call("live_light_start", {})
    monkeypatch.setattr(server.snapshot, "restore", lambda *_args: {"restored": True})
    assert controller.call("write", {"kind": "restore", "value": {}}) == {"restored": True}
    assert controller.live_light.session is None

    connect(controller)
    controller.call("live_light_start", {})
    monkeypatch.setattr(server.snapshot, "factory_reset", lambda *_args: {"reset_sent": True})
    result = controller.call("write", {"kind": "factory_reset"})
    assert result["reset_sent"] is True
    assert controller.live_light.session is None
