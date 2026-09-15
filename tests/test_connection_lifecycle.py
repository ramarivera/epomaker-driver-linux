"""Connection loss invalidates sessions without issuing configuration commands."""

from dataclasses import replace

import pytest

from epomaker_driver.discovery import DeviceInfo
from epomaker_driver.errors import DeviceUnavailable, ProtocolError
from epomaker_driver.server import Controller


@pytest.fixture
def connected(tmp_path, firmware, descriptor):
    info = DeviceInfo("/dev/hidraw-test", "Glyph", 5, 0x3151, 0x5004, descriptor, "bluetooth", 6)
    devices = [info]
    controller = Controller(
        tmp_path, discovery=lambda: list(devices), transport_factory=lambda _: firmware
    )
    controller.call("connect", {"path": info.path})
    yield controller, devices, firmware
    controller.close()


def test_poll_without_commands_and_return_copy(connected):
    controller, _, firmware = connected
    before = list(firmware.sent)
    identity = controller.call("connection", {})
    assert identity["path"] == "/dev/hidraw-test"
    identity["device_id"] = 0
    assert controller.call("connection", {})["device_id"] == 3059
    assert firmware.sent == before


def test_disappearance_clears_resources_and_does_not_reconnect(connected, monkeypatch):
    controller, devices, firmware = connected
    original = devices.pop()
    stopped = []
    monkeypatch.setattr(controller.audio_preview, "stop", lambda: stopped.append("audio"))
    monkeypatch.setattr(controller.system_info_refresh, "stop", lambda: stopped.append("stats"))
    controller.live_light.session = "active"
    controller.vendor_preview = ("token", {}, {})
    before = list(firmware.sent)
    assert controller.call("connection", {}) is None
    assert firmware.closed
    assert controller.keyboard is None
    assert controller.connection_info is None
    assert controller.live_light.session is None
    assert controller.vendor_preview is None
    assert stopped == ["audio", "stats"]
    devices.append(original)
    assert controller.call("connection", {}) is None
    assert len(controller.call("devices", {})) == 1
    assert firmware.sent == before


@pytest.mark.parametrize(
    "changes", [{"product_id": 0x5002}, {"descriptor": b"new"}, {"command_transport": None}]
)
def test_reused_path_or_changed_collection_drops_connection(connected, changes):
    controller, devices, firmware = connected
    devices[0] = replace(devices[0], **changes)
    assert controller.call("connection", {}) is None
    assert firmware.closed


def test_device_unavailable_operation_clears_state(connected, monkeypatch):
    controller, _, firmware = connected

    def fail():
        raise DeviceUnavailable("unplugged")

    monkeypatch.setattr(controller.keyboard, "status", fail)
    with pytest.raises(DeviceUnavailable, match="unplugged"):
        controller.call("read", {"section": "settings"})
    assert controller.keyboard is None
    assert firmware.closed


def test_failed_replacement_and_protocol_error_preserve_existing_connection(connected, monkeypatch):
    controller, _, firmware = connected
    identity = controller.call("connection", {})
    with pytest.raises(DeviceUnavailable):
        controller.call("connect", {"path": "/dev/missing"})
    assert controller.call("connection", {}) == identity

    def fail():
        raise ProtocolError("malformed response")

    monkeypatch.setattr(controller.keyboard, "status", fail)
    with pytest.raises(ProtocolError):
        controller.call("read", {"section": "settings"})
    assert controller.call("connection", {}) == identity
    assert not firmware.closed


def test_reconnect_changes_session(connected):
    controller, _, _ = connected
    first = controller.call("connection", {})
    second = controller.call("connect", {"path": first["path"]})
    assert second["session"] != first["session"]


def test_discovery_failure_is_not_disappearance(connected, monkeypatch):
    controller, _, firmware = connected

    def fail():
        raise OSError("sysfs temporarily unavailable")

    monkeypatch.setattr(controller, "discovery", fail)
    with pytest.raises(OSError):
        controller.call("connection", {})
    assert controller.keyboard is not None
    assert not firmware.closed
