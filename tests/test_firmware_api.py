import base64
import http.client
import io
import json
import threading
import zipfile
import zlib

import pytest

from epomaker_driver import server
from epomaker_driver.firmware_service import FirmwareServiceError


def raw_firmware():
    source = bytes(65536) + b"glyph"
    compressor = zlib.compressobj(wbits=-15)
    return compressor.compress(source) + compressor.flush()


def zip_firmware():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("firmwareFile.bin", bytes(65536) + b"main")
        archive.writestr("firmwareOledFile.bin", bytes(65536) + b"oled")
    return output.getvalue()


@pytest.fixture
def http_server(tmp_path):
    controller = server.Controller(tmp_path / "backups", discovery=lambda: [])
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("ok")
    with server.ControlServer(controller, web_root=web, token="token") as instance:
        worker = threading.Thread(target=instance.serve_forever, daemon=True)
        worker.start()
        yield instance
        instance.shutdown()
        worker.join()


def request(instance, path, *, method="GET", body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", instance.server_port, timeout=3)
    values = {"X-Epomaker-Token": "token", "Content-Type": "application/json"}
    values.update(headers or {})
    connection.request(method, path, body=body, headers=values)
    response = connection.getresponse()
    result = response.status, response.read()
    connection.close()
    return result


def test_inspect_is_offline_and_optional_comparison(tmp_path):
    controller = server.Controller(tmp_path / "backups", discovery=lambda: [])
    encoded = base64.b64encode(raw_firmware()).decode()
    result = controller.call(
        "firmware_inspect",
        {"content": encoded, "version": "usbv1", "current_versions": {"usb": 1}},
    )
    assert result["components"]["main"]["payload_length"] == 5
    assert result["comparison"]["candidates"][0]["reason"] == "not-newer"
    assert controller.keyboard is None
    controller.close()


def test_metadata_is_explicit_and_does_not_require_connection(tmp_path, monkeypatch):
    called = threading.Event()

    def fetch():
        called.set()
        return {"version_str": "usbv1", "write_ready": False}

    monkeypatch.setattr(server.firmware_service, "fetch_metadata", fetch)
    controller = server.Controller(tmp_path / "backups", discovery=lambda: [])
    assert controller.call("firmware_metadata", {})["version_str"] == "usbv1"
    assert called.is_set() and controller.keyboard is None
    controller.close()


def test_metadata_failure_is_actionable_and_does_not_close_controller(tmp_path, monkeypatch):
    monkeypatch.setattr(
        server.firmware_service,
        "fetch_metadata",
        lambda: (_ for _ in ()).throw(FirmwareServiceError("metadata unavailable")),
    )
    controller = server.Controller(tmp_path / "backups", discovery=lambda: [])
    with pytest.raises(FirmwareServiceError, match="metadata unavailable"):
        controller.call("firmware_metadata", {})
    assert controller.call("devices", {}) == []
    controller.close()


@pytest.mark.parametrize(
    "data, message",
    [
        ({"content": "!", "version": "usbv1"}, "base64"),
        ({"content": base64.b64encode(b"x").decode()}, "version"),
        ({"content": base64.b64encode(b"x").decode(), "version": ""}, "version"),
        ({"content": base64.b64encode(b"x").decode(), "version": " "}, "version"),
        ({"content": base64.b64encode(b"x").decode(), "version": "x" * 257}, "version"),
        (
            {
                "content": base64.b64encode(b"x").decode(),
                "version": "usbv1",
                "current_versions": [],
            },
            "current",
        ),
    ],
)
def test_inspect_validates_inputs(tmp_path, data, message):
    if data.get("current_versions") == []:
        data = {**data, "content": base64.b64encode(raw_firmware()).decode()}
    with pytest.raises(ValueError, match=message):
        server.Controller(tmp_path / "backups", discovery=lambda: []).call("firmware_inspect", data)


def test_http_metadata_auth_and_inspect_limits(http_server, monkeypatch):
    monkeypatch.setattr(server.firmware_service, "fetch_metadata", lambda: {"ok": True})
    assert (
        request(http_server, "/api/firmware_metadata", headers={"X-Epomaker-Token": ""})[0] == 403
    )
    assert (
        request(
            http_server,
            "/api/firmware_inspect",
            method="POST",
            body="{}",
            headers={"X-Epomaker-Token": ""},
        )[0]
        == 403
    )
    assert (
        request(
            http_server,
            "/api/firmware_inspect",
            method="POST",
            body="{}",
            headers={"Origin": "https://attacker.example"},
        )[0]
        == 403
    )
    assert request(http_server, "/api/firmware_metadata") == (200, b'{"ok": true}')
    status, _ = request(
        http_server,
        "/api/firmware_inspect",
        method="POST",
        body="{}",
        headers={"Content-Length": str(server.MAX_FIRMWARE_INSPECT_BODY + 1)},
    )
    assert status == 413


def test_http_inspect_returns_structural_result(http_server):
    body = json.dumps({"content": base64.b64encode(raw_firmware()).decode(), "version": "usbv1"})
    status, raw = request(http_server, "/api/firmware_inspect", method="POST", body=body)
    assert status == 200
    result = json.loads(raw)
    assert result["structural_only"] is True and result["write_ready"] is False


def test_http_inspect_accepts_versioned_zip(http_server):
    body = json.dumps(
        {
            "content": base64.b64encode(zip_firmware()).decode(),
            "version": "usbv1_oledv2",
        }
    )
    status, raw = request(http_server, "/api/firmware_inspect", method="POST", body=body)
    assert status == 200
    assert set(json.loads(raw)["components"]) == {"main", "oled"}


def test_inspect_enforces_decoded_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(server.firmware, "MAX_SIZE", 4)
    content = base64.b64encode(b"12345").decode()
    with pytest.raises(ValueError, match="size limit"):
        server.Controller(tmp_path / "backups", discovery=lambda: []).call(
            "firmware_inspect", {"content": content, "version": "usbv1"}
        )


def test_metadata_does_not_block_controller_operations(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    result, errors = [], []

    def blocked():
        entered.set()
        assert release.wait(1)
        return {}

    def invoke():
        try:
            result.append(controller.call("firmware_metadata", {}))
        except BaseException as error:  # pragma: no cover - diagnostic assertion below
            errors.append(error)

    controller = server.Controller(tmp_path / "backups", discovery=lambda: [])
    monkeypatch.setattr(server.firmware_service, "fetch_metadata", blocked)
    worker = threading.Thread(target=invoke)
    worker.start()
    assert entered.wait(1)
    try:
        assert controller.call("devices", {}) == []
        assert controller.call("disconnect", {}) == {"ok": True}
    finally:
        release.set()
    worker.join(1)
    assert not worker.is_alive()
    assert errors == [] and result == [{}]
    controller.close()


@pytest.mark.parametrize("data", [None, [], {"version": "usbv1"}, {"content": 1}, {"content": ""}])
def test_inspect_rejects_missing_or_nontext_payload(tmp_path, data):
    controller = server.Controller(tmp_path / "backups", discovery=lambda: [])
    with pytest.raises(ValueError):
        controller.call("firmware_inspect", data)


def test_oversized_encoded_input_is_rejected_before_decoding(tmp_path, monkeypatch):
    monkeypatch.setattr(server.firmware, "MAX_SIZE", 4)

    def unexpected_decode(*args, **kwargs):
        pytest.fail("oversized content must be rejected before decoding")

    monkeypatch.setattr(server.base64, "b64decode", unexpected_decode)
    controller = server.Controller(tmp_path / "backups", discovery=lambda: [])
    with pytest.raises(ValueError, match="size limit"):
        controller.call("firmware_inspect", {"content": "A" * 12, "version": "usbv1"})
