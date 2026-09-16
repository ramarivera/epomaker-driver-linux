import base64
import io
import json
import socket
import threading

import pytest
from PIL import Image

from epomaker_driver import media, server
from epomaker_driver.server import Controller


def image_bytes(*, animated=False):
    output = io.BytesIO()
    image = Image.new("RGB", (2, 2), "red")
    if animated:
        image.save(
            output,
            format="GIF",
            save_all=True,
            append_images=[Image.new("RGB", (2, 2), "blue")],
            duration=80,
        )
    else:
        image.save(output, format="PNG")
    return output.getvalue()


def asymmetric_bytes():
    image = Image.new("RGB", (2, 1))
    image.putdata([(1, 123, 250), (255, 0, 0)])
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_prepare_display_reuses_glyph_conversion_and_returns_quantized_preview():
    result = media.prepare_display(asymmetric_bytes(), kind="screen")
    assert result["width"] == 428
    assert result["height"] == 142
    assert result["frame_count"] == 1
    assert result["delay_ms"] is None
    assert result["pixel_bytes"] == 428 * 142 * 2
    preview = Image.open(io.BytesIO(base64.b64decode(result["preview_png"])))
    assert preview.size == (428, 142)
    assert preview.getpixel((0, 0)) == (0, 0, 0)
    assert preview.getpixel((100, 71)) == (0, 134, 255)
    assert preview.getpixel((300, 71)) == (255, 0, 0)


def test_prepare_display_supports_rgb24_preview():
    image = Image.new("RGB", (60, 9), "black")
    image.putpixel((0, 0), (1, 2, 3))
    output = io.BytesIO()
    image.save(output, format="PNG")
    result = media.prepare_display(output.getvalue(), kind="screen", model_id=1723)
    preview = Image.open(io.BytesIO(base64.b64decode(result["preview_png"])))
    assert result["pixel_bytes"] == 60 * 9 * 3
    assert preview.size == (60, 9)
    assert preview.getpixel((0, 0)) == (1, 2, 3)


def test_prepare_display_animation_reports_delay_and_all_frame_bytes():
    result = media.prepare_display(image_bytes(animated=True), kind="animation")
    assert result["frame_count"] == 2
    assert result["delay_ms"] == 80
    assert result["pixel_bytes"] == 2 * 428 * 142 * 2
    assert len(result["preview_frames"]) == 2
    assert result["preview_png"] == result["preview_frames"][0]
    first = Image.open(io.BytesIO(base64.b64decode(result["preview_frames"][0])))
    second = Image.open(io.BytesIO(base64.b64decode(result["preview_frames"][1])))
    assert first.getpixel((214, 71)) == (255, 0, 0)
    assert second.getpixel((214, 71)) == (0, 0, 255)


def test_prepare_display_animation_preserves_zero_delay():
    result = media.prepare_display(image_bytes(animated=True), kind="animation", delay_ms=0)
    assert result["delay_ms"] == 0
    assert len(result["preview_frames"]) == result["frame_count"]


@pytest.mark.parametrize(
    "kind,content,delay,message",
    [
        ("other", image_bytes(), None, "kind"),
        ("screen", b"", None, "nonempty"),
        ("screen", b"not an image", None, "cannot identify image"),
        ("animation", image_bytes(), None, "animation must contain"),
        ("animation", image_bytes(animated=True), True, "frame delay"),
    ],
)
def test_prepare_display_rejects_invalid_input_before_hid(kind, content, delay, message):
    with pytest.raises((ValueError, OSError), match=message):
        media.prepare_display(content, kind=kind, delay_ms=delay)


@pytest.fixture
def http_server(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("ok")

    def fail_discovery():
        raise AssertionError("display preparation must not discover a device")

    controller = Controller(tmp_path / "backups", discovery=fail_discovery)
    with server.ControlServer(controller, web_root=web, token="test-token") as instance:
        worker = threading.Thread(target=instance.serve_forever, daemon=True)
        worker.start()
        yield instance
        instance.shutdown()
        worker.join()


def test_display_prepare_http_is_offline_and_token_protected(http_server):
    content = base64.b64encode(image_bytes()).decode()
    body = json.dumps({"kind": "screen", "content": content})
    status, value, _ = server_request(
        http_server, "/api/display_prepare", body=body, token="test-token"
    )
    assert status == 200
    assert value["width"] == 428 and value["frame_count"] == 1
    assert http_server.controller.keyboard is None
    status, _, _ = server_request(http_server, "/api/display_prepare", body=body)
    assert status == 403


@pytest.mark.parametrize(
    "payload,message",
    [
        ({"kind": "screen"}, "base64 string"),
        ({"kind": "screen", "content": "%%%"}, ""),
    ],
)
def test_display_prepare_http_rejects_bad_content(http_server, payload, message):
    status, value, _ = server_request(
        http_server,
        "/api/display_prepare",
        body=json.dumps(payload),
        token="test-token",
    )
    assert status == 400
    if message:
        assert message in value["error"]


def test_display_prepare_http_enforces_request_limit(http_server):
    request = (
        f"POST /api/display_prepare HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{http_server.server_port}\r\n"
        "Content-Type: application/json\r\n"
        "X-Epomaker-Token: test-token\r\n"
        f"Content-Length: {server.MAX_BODY + 1}\r\n\r\n"
    ).encode()
    with socket.create_connection(("127.0.0.1", http_server.server_port)) as connection:
        connection.sendall(request)
        response = connection.recv(4096)
    assert response.startswith(b"HTTP/1.0 413")


def server_request(instance, path, *, body, token=None):
    import http.client

    connection = http.client.HTTPConnection("127.0.0.1", instance.server_port)
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-Epomaker-Token"] = token
    connection.request("POST", path, body=body, headers=headers)
    response = connection.getresponse()
    raw = response.read()
    return response.status, json.loads(raw), response.headers


def test_display_edit_http_preserves_library_frames_without_device_access(http_server):
    body = json.dumps(
        {
            "kind": "screen",
            "content": base64.b64encode(image_bytes()).decode(),
            "operation": "add",
            "index": 0,
        }
    )
    status, _, _ = server_request(http_server, "/api/display_edit", body=body)
    assert status == 403
    status, edited, _ = server_request(
        http_server, "/api/display_edit", body=body, token="test-token"
    )
    assert status == 200
    assert edited["kind"] == "animation" and edited["frame_count"] == 2
    assert edited["selected_index"] == 1 and edited["delay_ms"] == 80
    controller = http_server.controller
    entry = controller.call("display_asset_save", {**edited, "name": "Edited frames"})
    loaded = controller.call("display_asset_get", {"id": entry["id"]})
    assert loaded["preview_frames"] == edited["preview_frames"]
    assert loaded["content"] == edited["content"]
    assert controller.keyboard is None
    for operation in ([], {}, "unknown"):
        status, error, _ = server_request(
            http_server,
            "/api/display_edit",
            body=json.dumps(
                {
                    "kind": "screen",
                    "content": base64.b64encode(image_bytes()).decode(),
                    "operation": operation,
                    "index": 0,
                }
            ),
            token="test-token",
        )
        assert status == 400 and "operation" in error["error"]


@pytest.mark.parametrize(
    "replacement,message",
    [
        (False, "base64 PNG"),
        ("", "base64 PNG"),
        ([], "base64 PNG"),
        ("x" * (4 * ((1024 * 1024 + 2) // 3) + 1), "1 MiB"),
    ],
)
def test_display_replacement_api_rejects_invalid_encoded_data(tmp_path, replacement, message):
    controller = Controller(tmp_path)
    with pytest.raises(ValueError, match=message):
        controller.call(
            "display_edit",
            {
                "content": base64.b64encode(image_bytes()).decode(),
                "kind": "screen",
                "operation": "replace",
                "index": 0,
                "replacement": replacement,
            },
        )
    assert controller.keyboard is None


def test_display_replace_http_quantizes_and_preserves_other_animation_frames(http_server):
    output = io.BytesIO()
    Image.new("RGB", (428, 142), (250, 120, 7)).save(output, format="PNG")
    body = {
        "content": base64.b64encode(image_bytes(animated=True)).decode(),
        "kind": "animation",
        "delay_ms": 0,
        "operation": "replace",
        "index": 1,
        "replacement": base64.b64encode(output.getvalue()).decode(),
    }
    status, result, _ = server_request(
        http_server, "/api/display_edit", body=json.dumps(body), token="test-token"
    )
    assert status == 200 and result["frame_count"] == 2 and result["delay_ms"] == 0
    expected = media.prepare_display(image_bytes(animated=True), kind="animation", delay_ms=0)
    assert result["preview_frames"][0] == expected["preview_frames"][0]
    image = Image.open(io.BytesIO(base64.b64decode(result["preview_frames"][1])))
    assert image.getpixel((15, 20)) == (255, 121, 0)
    assert http_server.controller.keyboard is None


@pytest.mark.parametrize("operation", ["display_import_inspect", "display_import_transform"])
def test_display_import_http_is_offline_and_token_protected(http_server, operation):
    body = json.dumps(
        {"content": base64.b64encode(image_bytes()).decode(), "scale": 100, "x": 0, "y": 0}
    )
    status, _, _ = server_request(http_server, f"/api/{operation}", body=body)
    assert status == 403
    status, result, _ = server_request(
        http_server, f"/api/{operation}", body=body, token="test-token"
    )
    assert status == 200 and result["frame_count"] == 1
    assert result["replace_all"] is False and result["preview_png"]
    assert http_server.controller.keyboard is None
