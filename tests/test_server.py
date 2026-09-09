import base64
import http.client
import io
import json
import threading

import pytest
from PIL import Image

from epomaker_driver import cli, server
from epomaker_driver.discovery import DeviceInfo
from epomaker_driver.errors import DeviceUnavailable, ProtocolError, UnsupportedDevice


@pytest.fixture
def controller(tmp_path, firmware, descriptor):
    info = DeviceInfo(
        "/dev/hidraw-test", "Glyph simulator", 5, 0x3151, 0x5004, descriptor, "bluetooth", 6
    )
    return server.Controller(
        tmp_path / "backups", discovery=lambda: [info], transport_factory=lambda _: firmware
    )


def connect(controller):
    return controller.call("connect", {"path": "/dev/hidraw-test"})


def test_connection_and_catalog(controller, firmware):
    assert controller.call("connection", {}) is None
    assert controller.call("devices", {})[0]["vendor_id"] == "3151"
    catalog = controller.call("catalog", {})
    assert len(catalog["matrices"]) == 3
    assert len(catalog["matrices"][0]) == 512
    with pytest.raises(DeviceUnavailable):
        controller.call("read", {})
    with pytest.raises(DeviceUnavailable):
        controller.call("connect", {"path": "/tmp/arbitrary"})
    assert connect(controller) == controller.call("connection", {})
    connect(controller)
    assert firmware.closed
    assert controller.call("disconnect", {}) == {"ok": True}
    assert controller.keyboard is None
    controller.close()


def test_failed_connection_closes_transport(controller, firmware):
    firmware.model_id = 9999
    with pytest.raises(Exception, match="Unknown internal device"):
        connect(controller)
    assert firmware.closed
    assert controller.keyboard is None


def test_controller_configuration(controller, firmware):
    connect(controller)

    def write(**data):
        return controller.call("write", data)

    write(kind="key", slot=0, action="05000000")
    matrix = controller.call("read", {"section": "keymap"})
    assert matrix["raw"][:4] == [5, 0, 0, 0]
    assert len(matrix["slots"]) == 128
    write(kind="lighting", mode="solid", side=False, rgb=0x010203, brightness=3, speed=2)
    assert controller.call("read", {"section": "lighting"})["main"]["rgb"] == 0x010203
    write(kind="picture", index=2, colors="abcdef" * 126)
    assert controller.call("read", {"section": "picture", "index": 2})["colors"] == "abcdef" * 126
    value = {"repeat": 2, "events": [{"hid_usage": 4, "down": True, "delay_ms": 10}]}
    write(kind="macro", slot=1, value=value)
    assert controller.call("read", {"section": "macro", "slot": 1})["decoded"] == value
    firmware.macros[2] = bytearray(bytes([0, 0, 255, 1]) + bytes(252))
    assert "decode_error" in controller.call("read", {"section": "macro", "slot": 2})
    write(kind="profile", profile=2)
    write(kind="debounce", milliseconds=8)
    write(kind="sleep", bt=120, dongle=240, deep_bt=1800, deep_dongle=3600)
    write(kind="options", system="mac", wasd_swap=True)
    write(kind="auto_os", enabled=True)
    result = controller.call("read", {"section": "settings"})
    assert result["auto_os"] is True
    assert firmware.profile == 2 and firmware.debounce == 8
    for operation, data in [("read", {}), ("write", {}), ("unknown", {})]:
        with pytest.raises(ValueError, match="unknown"):
            controller.call(operation, data)


def test_controller_backup_and_restore(controller):
    connect(controller)
    value = controller.call("read", {"section": "backup"})
    result = controller.call("write", {"kind": "restore", "value": value})
    assert result
    assert len(list(controller.backup_dir.glob("recovery-*.json"))) == 1


def test_controller_factory_reset_is_glyph_only_and_requires_reconnect(controller, firmware):
    connect(controller)
    result = controller.call("write", {"kind": "factory_reset"})
    assert result["reset_sent"] is True
    assert result["factory_defaults_verified"] is False
    assert result["connection"] == {
        "state": "disconnected",
        "reconnect_required": True,
        "factory_defaults_verified": False,
    }
    assert controller.identity is None and controller.keyboard is None
    recovery = list(controller.backup_dir.glob("recovery-*.json"))
    assert len(recovery) == 1 and str(recovery[0]) == result["previous_configuration"]


def test_controller_factory_reset_failure_keeps_recovery_and_drops_connection(controller, firmware):
    connect(controller)

    def fail_send(*args, **kwargs):
        raise OSError("simulated disconnect after reset")

    firmware.send = fail_send
    with pytest.raises(ProtocolError, match="recovery snapshot is saved at"):
        controller.call("write", {"kind": "factory_reset"})
    assert controller.identity is None and controller.keyboard is None
    assert len(list(controller.backup_dir.glob("recovery-*.json"))) == 1


def test_controller_factory_reset_rechecks_identity_before_reset(controller, firmware):
    connect(controller)
    firmware.model_id = 2895
    with pytest.raises(UnsupportedDevice, match="Glyph only"):
        controller.call("write", {"kind": "factory_reset"})
    assert controller.identity is None and controller.keyboard is None
    assert not [command for command in firmware.sent if command[0] == 1]
    assert not list(controller.backup_dir.glob("recovery-*.json"))


def test_controller_reset_backup_failure_prevents_send(controller, firmware, monkeypatch):
    connect(controller)

    def failed_capture(*args, **kwargs):
        raise ProtocolError("macro read failed")

    monkeypatch.setattr(controller.keyboard, "read_macro", failed_capture)
    with pytest.raises(ProtocolError, match="macro read failed"):
        controller.call("write", {"kind": "factory_reset"})
    assert firmware.closed
    assert controller.keyboard is None and controller.identity is None
    assert not firmware.sent
    assert not list(controller.backup_dir.glob("recovery-*.json"))


def test_controller_display(controller, monkeypatch):
    connect(controller)
    output = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(output, format="PNG")
    controller.call(
        "write", {"kind": "screen", "content": base64.b64encode(output.getvalue()).decode()}
    )
    output = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(
        output,
        format="GIF",
        save_all=True,
        append_images=[Image.new("RGB", (2, 2), "blue")],
        duration=100,
    )
    controller.call(
        "write", {"kind": "animation", "content": base64.b64encode(output.getvalue()).decode()}
    )
    controller.call("write", {"kind": "clock"})
    monkeypatch.setattr(server.system_info.Collector, "collect", lambda _: {})
    monkeypatch.setattr(server.Keyboard, "sync_system_info", lambda *args: None)
    assert controller.call("write", {"kind": "system_info"}) == {}


@pytest.fixture
def http_server(controller, tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<h1>EPOMAKER</h1>")
    (web / "binary").write_bytes(b"abc")
    (tmp_path / "outside").write_text("private")
    (web / "link").symlink_to(tmp_path / "outside")
    with server.ControlServer(controller, web_root=web, token="test-token") as instance:
        worker = threading.Thread(target=instance.serve_forever, daemon=True)
        worker.start()
        yield instance
        instance.shutdown()
        worker.join()


def request(instance, path="/api/devices", *, method="GET", body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", instance.server_port, timeout=3)
    values = {"X-Epomaker-Token": "test-token", "Content-Type": "application/json"}
    values.update(headers or {})
    connection.request(method, path, body=body, headers=values)
    response = connection.getresponse()
    result = response.status, response.read(), dict(response.getheaders())
    connection.close()
    return result


def test_http_assets_and_api(http_server):
    status, body, headers = request(http_server, "/")
    assert status == 200 and b"EPOMAKER" in body
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert request(http_server, "/binary")[2]["Content-Type"] == "application/octet-stream"
    for path in ["/missing", "/%2e%2e/outside", "/link", "/api/missing"]:
        assert request(http_server, path)[0] == 404
    assert request(http_server)[0] == 200
    assert request(http_server, "/api/catalog")[0] == 200
    assert request(http_server, "/api/connection")[1] == b"null"
    assert (
        request(
            http_server,
            "/api/connect",
            method="POST",
            body=json.dumps({"path": "/dev/hidraw-test"}),
        )[0]
        == 200
    )
    assert request(http_server, "/api/read", method="POST", body="{}")[0] == 400
    assert request(http_server, "/api/disconnect", method="POST", body="{}")[0] == 200


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "attacker.example"},
        {"Origin": "https://attacker.example"},
        {"X-Epomaker-Token": ""},
        {"X-Epomaker-Token": "é"},
    ],
)
def test_http_security(http_server, headers):
    assert request(http_server, headers=headers)[0] == 403
    assert request(http_server, "/api/write", method="POST", body="{}", headers=headers)[0] == 403


@pytest.mark.parametrize(
    "path,body,headers,status",
    [
        ("/api/missing", "{}", {}, 404),
        ("/api/write", "{}", {"Content-Length": "0"}, 413),
        ("/api/write", "{}", {"Content-Length": str(server.MAX_BODY + 1)}, 413),
        ("/api/write", "{}", {"Transfer-Encoding": "chunked"}, 413),
        ("/api/write", "{}", {"Content-Type": "text/plain"}, 415),
        ("/api/write", "{}", {"Content-Length": "invalid"}, 400),
        ("/api/write", "[]", {}, 400),
        ("/api/write", "invalid", {}, 400),
        ("/api/write", "{}", {}, 400),
    ],
)
def test_http_rejects_bad_requests(http_server, path, body, headers, status):
    assert request(http_server, path, method="POST", body=body, headers=headers)[0] == status


def test_serve_cli(monkeypatch, capsys):
    monkeypatch.setattr(server.ControlServer, "serve_forever", lambda _: None)
    assert cli.main(["serve", "--port", "0"]) == 0
    assert "/#token=" in capsys.readouterr().out
    assert cli.main(["serve", "--port", "-1"]) == 1


def test_offline_macro_validation(controller):
    value = {"repeat": 1, "events": []}
    assert controller.call("validate_macro", {"value": value}) == value
    with pytest.raises(ValueError, match="each event"):
        controller.call("validate_macro", {"value": {"repeat": 1, "events": [None]}})


def test_display_bank_api(controller, firmware):
    connect(controller)
    output = io.BytesIO()
    Image.new("RGB", (1, 1), "blue").save(output, format="PNG")
    data = {"kind": "screen", "bank": 4, "content": base64.b64encode(output.getvalue()).decode()}
    controller.call("write", data)
    assert all(p[1:3] == bytes([4, 1]) for p in firmware.sent if p[0] == 0x25)
    before = list(firmware.sent)
    with pytest.raises(ValueError, match="still bank"):
        controller.call("write", {**data, "bank": 5})
    assert firmware.sent == before
    controller.call("write", {"kind": "display_language_toggle"})
    assert firmware.sent[-1][:2] == bytes([0x27, 1])


def test_rt85_does_not_enter_glyph_interface(controller, firmware):
    firmware.model_id = 2895
    with pytest.raises(Exception, match="use the CLI for RT85"):
        connect(controller)
    assert firmware.closed
    assert controller.keyboard is None
    assert firmware.sent == []
