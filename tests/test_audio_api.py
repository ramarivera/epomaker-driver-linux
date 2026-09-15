import http.client
import json
import threading

import pytest

from epomaker_driver.audio_capture import AudioCaptureError
from epomaker_driver.server import Controller, ControlServer


class Preview:
    def __init__(self):
        self.calls = []

    def start(self, target, **settings):
        self.calls.append(("start", target, settings))
        return {"session": "preview"}

    def sample(self, token):
        self.calls.append(("sample", token))
        return {"running": True, "bands": [0.5] * 32}

    def stop(self, token=None):
        self.calls.append(("stop", token))
        return {"ok": True}


@pytest.fixture
def controller(tmp_path):
    ctl = Controller(tmp_path, audio_discovery=lambda: [{"id": "12", "name": "Speakers"}])
    ctl.audio_preview = Preview()
    return ctl


def test_audio_api_works_without_keyboard_and_validates_output(controller):
    assert controller.call("audio_outputs", {}) == [{"id": "12", "name": "Speakers"}]
    config = controller.call("audio_config", {})
    assert config["defaults"]["gain"] == 10
    assert config["limits"]["gain"] == {"min": 1, "max": 20, "step": 1}
    assert controller.call("audio_preview_start", {"target": "12", "settings": {"gain": 4}}) == {
        "session": "preview"
    }
    assert controller.audio_preview.calls[-1] == ("start", "12", {"gain": 4})
    assert controller.call("audio_preview_start", {}) == {"session": "preview"}
    assert controller.call("audio_preview_sample", {"session": "preview"})["bands"] == [0.5] * 32
    assert controller.call("audio_preview_stop", {"session": "preview"}) == {"ok": True}
    for data in (
        {"target": "microphone"},
        {"target": None},
        {"settings": []},
        {"settings": {"unknown": 1}},
    ):
        with pytest.raises(ValueError):
            controller.call("audio_preview_start", data)
    for operation in ("audio_preview_sample", "audio_preview_stop"):
        for token in (None, "", 1):
            with pytest.raises(ValueError, match="session"):
                controller.call(operation, {"session": token})
    controller.call("disconnect", {})
    assert controller.audio_preview.calls[-1] == ("stop", None)


def test_audio_routes_require_auth_and_report_discovery_errors(controller, tmp_path):
    def request(server, path, data=None, token="test"):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        connection.request(
            "GET" if data is None else "POST",
            "/api/" + path,
            body=None if data is None else json.dumps(data),
            headers={"X-Epomaker-Token": token, "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    with ControlServer(controller, token="test", web_root=tmp_path) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            for path, body in (
                ("audio_config", None),
                ("audio_outputs", None),
                ("audio_preview_start", {}),
                ("audio_preview_sample", {"session": "preview"}),
                ("audio_preview_stop", {"session": "preview"}),
            ):
                assert request(server, path, body, token="wrong")[0] == 403
                assert request(server, path, body)[0] == 200

            def fail():
                raise AudioCaptureError("pw-dump unavailable")

            controller.audio_discovery = fail
            code, body = request(server, "audio_outputs")
            assert code == 400 and body["error"] == "pw-dump unavailable"
        finally:
            server.shutdown()
            worker.join()
