import base64
import json

import pytest

from epomaker_driver import profiles
from epomaker_driver.device import Keyboard
from epomaker_driver.errors import DeviceUnavailable, UnsupportedDevice
from epomaker_driver.server import Controller


@pytest.fixture
def controller(tmp_path, firmware):
    value = Controller(tmp_path / "backups")
    value.keyboard = Keyboard(firmware)
    return value


def content(fn=False):
    return base64.b64encode(
        profiles.encode(
            {
                "deviceType": {"id": 3059},
                "fn": fn,
                "value": [
                    {
                        "type": "ConfigMacro",
                        "original": 4,
                        "macroType": "on_off",
                        "repeatCount": 1,
                        "macro": [],
                    },
                ],
            }
        )
    ).decode()


def preview(controller, **extra):
    return controller.call("vendor_import_preview", {"content": content(), **extra})


def test_preview_apply_and_single_use(controller, firmware):
    result = preview(controller)
    assert not firmware.sent
    assert not controller.backup_dir.exists()
    applied = controller.call(
        "write",
        {"kind": "vendor_import", "token": result["token"], "target": "Fn Mac", "profile": 2},
    )
    assert applied["target"] == "Main" and applied["profile"] == 0
    assert (
        len(json.loads(next(controller.backup_dir.glob("recovery-*.json")).read_text())["macros"])
        == 256
    )
    with pytest.raises(ValueError, match="preview"):
        controller.call("write", {"kind": "vendor_import", "token": result["token"]})


def test_new_preview_invalidates_old_token(controller):
    first = preview(controller)
    second = preview(controller)
    with pytest.raises(ValueError, match="preview"):
        controller.call("write", {"kind": "vendor_import", "token": first["token"]})
    assert controller.call("write", {"kind": "vendor_import", "token": second["token"]})["imported"]


def test_changed_allocation_requires_new_preview_before_backup(controller, firmware):
    result = preview(controller)
    firmware.fn[1][0:4] = bytes([9, 1, 0, 0])
    with pytest.raises(ValueError, match="allocation changed"):
        controller.call("write", {"kind": "vendor_import", "token": result["token"]})
    assert not firmware.sent
    assert not controller.backup_dir.exists()


def test_close_discards_pending_preview(controller):
    preview(controller)
    controller.close()
    assert controller.vendor_preview is None
    with pytest.raises(DeviceUnavailable):
        preview(controller)


@pytest.mark.parametrize(
    "value", [None, "", "!", base64.b64encode(b"bad json").decode(), "A" * 11184813]
)
def test_malformed_file_invalidates_previous_preview(controller, firmware, value):
    preview(controller)
    with pytest.raises(ValueError):
        preview(controller, content=value)
    assert controller.vendor_preview is None
    assert not firmware.sent


def test_wrong_connected_model(controller, firmware):
    firmware.model_id = 2895
    with pytest.raises(UnsupportedDevice, match="Glyph only"):
        preview(controller)
    assert not firmware.sent


def test_returned_plan_is_not_mutable_server_state(controller):
    result = preview(controller)
    result["plan"]["profile"] = 2
    assert controller.vendor_preview[2]["profile"] == 0


def test_http_preview_endpoint_requires_auth_and_returns_plan(controller):
    import http.client
    import threading

    from epomaker_driver.server import ControlServer

    with ControlServer(controller, token="test-token") as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection(*server.server_address)
        body = json.dumps({"content": content()})
        try:
            connection.request(
                "POST", "/api/vendor_import_preview", body, {"Content-Type": "application/json"}
            )
            response = connection.getresponse()
            assert response.status == 403
            response.read()
            connection.request(
                "POST",
                "/api/vendor_import_preview",
                body,
                {"Content-Type": "application/json", "X-Epomaker-Token": "test-token"},
            )
            response = connection.getresponse()
            assert response.status == 200
            assert json.loads(response.read())["plan"]["target"] == "Main"
        finally:
            connection.close()
            server.shutdown()
            thread.join()
