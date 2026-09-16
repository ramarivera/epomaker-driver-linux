"""Controller-level screen erase safety tests; no HID device is opened."""

import http.client
import json
import threading
import time

import pytest

from epomaker_driver import server
from epomaker_driver.errors import ProtocolError, UnsupportedDevice


@pytest.fixture
def http_server(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("screen erase test")
    controller = server.Controller(tmp_path / "backups", discovery=lambda: [])
    with server.ControlServer(controller, web_root=web, token="test-token") as instance:
        worker = threading.Thread(target=instance.serve_forever, daemon=True)
        worker.start()
        yield instance
        instance.shutdown()
        worker.join()


def http_request(instance, path, token="test-token"):
    connection = http.client.HTTPConnection("127.0.0.1", instance.server_port, timeout=3)
    connection.request("GET", path, headers={"X-Epomaker-Token": token})
    response = connection.getresponse()
    result = response.status, response.read()
    connection.close()
    return result


def http_post(instance, path, body, token="test-token"):
    connection = http.client.HTTPConnection("127.0.0.1", instance.server_port, timeout=3)
    connection.request(
        "POST",
        path,
        body=json.dumps(body),
        headers={"X-Epomaker-Token": token, "Content-Type": "application/json"},
    )
    response = connection.getresponse()
    result = response.status, response.read()
    connection.close()
    return result


class FakeTransport:
    def __init__(self, vendor_reports=None):
        self.vendor_reports = vendor_reports if vendor_reports is not None else {6: 64}
        self.closed = False
        self.telemetry_calls = 0

    def telemetry(self):
        self.telemetry_calls += 1
        raise AssertionError("telemetry must not be polled during screen erase")

    def close(self):
        self.closed = True


class BlockingKeyboard:
    def __init__(self, transport, result=None, error=None, events=None):
        self.transport = transport
        self.entered = threading.Event()
        self.release = threading.Event()
        self.result = result if result is not None else {}
        self.error = error
        self.events = events

    def erase_screen(self, *, cancel, progress):
        if self.events is not None:
            self.events.append("keyboard.entered")
        self.entered.set()
        while not self.release.is_set():
            if cancel.is_set():
                raise OSError("erase cancelled by disconnect")
            time.sleep(0.001)
        if self.error is not None:
            raise self.error
        return self.result


def make_controller(tmp_path, keyboard, *, identity_session="session-a"):
    controller = server.Controller(tmp_path / "backups", discovery=lambda: [])
    controller.keyboard = keyboard
    controller.identity = {"device_id": 3059, "session": identity_session}
    return controller


def wait_for_state(controller, state):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        status = controller.call("screen_erase", {})
        if status["state"] == state:
            return status
        time.sleep(0.005)
    pytest.fail(f"screen erase did not reach {state}: {controller.call('screen_erase', {})}")


def test_start_requires_confirmation_and_current_session(tmp_path):
    keyboard = BlockingKeyboard(FakeTransport())
    controller = make_controller(tmp_path, keyboard)
    with pytest.raises(ValueError, match="confirm"):
        controller.call("screen_erase_start", {"session": "session-a"})
    with pytest.raises(ValueError, match="connection changed"):
        controller.call("screen_erase_start", {"confirm": True, "session": "stale-session"})
    assert not keyboard.entered.is_set()
    controller.close()


def test_start_rejects_connection_without_vendor_reports(tmp_path):
    keyboard = BlockingKeyboard(FakeTransport(vendor_reports={}))
    controller = make_controller(tmp_path, keyboard)
    with pytest.raises(UnsupportedDevice, match="completion input report"):
        controller.call("screen_erase_start", {"confirm": True, "session": "session-a"})
    assert controller.call("screen_erase", {})["state"] == "idle"
    assert not keyboard.entered.is_set()
    controller.close()


def test_active_erase_blocks_hid_but_keeps_offline_calls_and_skips_telemetry(tmp_path):
    keyboard = BlockingKeyboard(FakeTransport())
    controller = make_controller(tmp_path, keyboard)
    controller.call("screen_erase_start", {"confirm": True, "session": "session-a"})
    assert keyboard.entered.wait(1)
    with pytest.raises(ProtocolError, match="blocks device access"):
        controller.call("read", {"section": "settings"})
    assert controller.call("catalog", {})["matrices"]
    assert controller.call("validate_macro", {"value": {"repeat": 1, "events": []}})
    assert controller.call("connection", {})["telemetry"] is None
    assert keyboard.transport.telemetry_calls == 0
    controller.call("disconnect", {})
    assert controller.call("screen_erase", {})["state"] == "uncertain"


@pytest.mark.parametrize(
    "operation,data",
    [
        ("connect", {"path": "/dev/other"}),
        ("read", {"section": "settings"}),
        ("write", {}),
        ("vendor_import_preview", {}),
        ("system_info_refresh_start", {}),
        ("live_light_start", {}),
        ("live_light_frame", {}),
        ("live_light_stop", {}),
        ("screen_erase_start", {"confirm": True, "session": "session-a"}),
    ],
)
@pytest.mark.parametrize("outcome", ["active", "uncertain"])
def test_all_hid_endpoints_blocked_during_active_or_uncertain_erase(
    tmp_path, operation, data, outcome
):
    keyboard = BlockingKeyboard(FakeTransport())
    controller = make_controller(tmp_path, keyboard)
    controller.call("screen_erase_start", {"confirm": True, "session": "session-a"})
    assert keyboard.entered.wait(1)
    if outcome == "uncertain":
        keyboard.release.set()
        wait_for_state(controller, "uncertain")
    with pytest.raises(ProtocolError, match="blocks device access"):
        controller.call(operation, data)
    assert keyboard.transport.telemetry_calls == 0
    controller.close()


def test_disconnect_cancels_erase_and_journals_uncertain(tmp_path):
    keyboard = BlockingKeyboard(FakeTransport())
    controller = make_controller(tmp_path, keyboard)
    controller.call("screen_erase_start", {"confirm": True, "session": "session-a"})
    assert keyboard.entered.wait(1)
    assert controller.call("disconnect", {}) == {"ok": True}
    status = controller.call("screen_erase", {})
    assert status["state"] == "uncertain"
    assert status["blocked"] is True and "cancelled" in status["error"]
    journal = json.loads((controller.backup_dir / "screen-erase.json").read_text())
    assert journal["state"] == "uncertain" and journal["blocked"] is True
    assert keyboard.transport.closed
    assert controller.call("catalog", {})["matrices"]


def test_stale_ack_does_not_close_connection_exact_ack_does(tmp_path):
    keyboard = BlockingKeyboard(FakeTransport())
    controller = make_controller(tmp_path, keyboard)
    controller.call("screen_erase_start", {"confirm": True, "session": "session-a"})
    assert keyboard.entered.wait(1)
    keyboard.release.set()
    status = wait_for_state(controller, "uncertain")
    with pytest.raises(ValueError, match="does not match"):
        controller.call(
            "screen_erase_acknowledge",
            {"confirm": True, "operation_id": "stale-operation"},
        )
    assert not keyboard.transport.closed
    result = controller.call(
        "screen_erase_acknowledge",
        {"confirm": True, "operation_id": status["operation_id"]},
    )
    assert result["state"] == "acknowledged"
    assert keyboard.transport.closed
    assert controller.identity is None and controller.keyboard is None


def test_start_stops_refresh_live_session_and_clears_preview(tmp_path):
    events = []
    keyboard = BlockingKeyboard(FakeTransport(), events=events)
    controller = make_controller(tmp_path, keyboard)
    refresh_stops = []
    live_stops = []
    controller.system_info_refresh.stop = lambda: (
        refresh_stops.append(True),
        events.append("refresh.stop"),
    )
    controller.live_light.session = "live-session"
    controller.live_light.stop = lambda session: (
        live_stops.append(session),
        events.append("live.stop"),
    )
    controller.vendor_preview = ("token", object(), {})
    controller.call("screen_erase_start", {"confirm": True, "session": "session-a"})
    assert keyboard.entered.wait(1)
    assert refresh_stops and live_stops == ["live-session"]
    assert events[:3] == ["refresh.stop", "live.stop", "keyboard.entered"]
    assert controller.vendor_preview is None
    controller.call("disconnect", {})


def test_http_screen_erase_endpoint_requires_token(http_server):
    assert http_request(http_server, "/api/screen_erase", token="")[0] == 403
    status, body = http_request(http_server, "/api/screen_erase")
    assert status == 200
    assert json.loads(body)["state"] == "idle"


def test_http_screen_erase_post_authorization_and_preflight(http_server):
    body = {"confirm": True, "session": "session-a"}
    assert http_post(http_server, "/api/screen_erase_start", body, token="")[0] == 403
    status, response = http_post(http_server, "/api/screen_erase_start", body)
    assert status == 400 and json.loads(response)["type"] == "DeviceUnavailable"
    http_server.controller.keyboard = BlockingKeyboard(FakeTransport())
    http_server.controller.identity = {"device_id": 3059, "session": "session-a"}
    status, response = http_post(http_server, "/api/screen_erase_acknowledge", {})
    assert status == 400 and json.loads(response)["type"] == "ValueError"
    assert http_server.controller.identity["session"] == "session-a"
