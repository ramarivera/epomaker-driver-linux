import http.client
import json
import threading

import pytest

from epomaker_driver import macro_library, profiles, server

VALUE = {"repeat": 1, "events": [{"hid_usage": 4, "down": True, "delay_ms": 10}]}


def test_crud_restart_and_revision_conflicts(tmp_path):
    path = tmp_path / "library"
    controller = server.Controller(tmp_path / "backups", library_dir=path)
    assert controller.call("macro_library", {}) == {"entries": []}
    assert not path.exists()
    entry = controller.call(
        "macro_library_save", {"name": "  Alpha ", "value": VALUE, "mode": "count"}
    )
    assert entry["name"] == "Alpha" and entry["revision"] == 1
    assert entry["id"] == entry["id"].lower() and len(entry["id"]) == 32
    assert (path / f"{entry['id']}.json").stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="conflict"):
        controller.call("macro_library_save", {**entry, "name": "stale", "revision": 2})
    updated = controller.call("macro_library_save", {**entry, "name": "Beta"})
    assert updated["revision"] == 2
    restarted = server.Controller(tmp_path / "other", library_dir=path)
    assert restarted.call("macro_library", {}) == {"entries": [updated]}
    assert controller.call("macro_library_delete", {"id": updated["id"], "revision": 2}) == {
        "ok": True
    }
    with pytest.raises(ValueError, match="does not exist"):
        restarted.call("macro_library_delete", {"id": updated["id"], "revision": 2})


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"name": "", "value": VALUE, "mode": "count"}, "blank"),
        ({"name": "x" * 21, "value": VALUE, "mode": "count"}, "20"),
        ({"name": "x", "value": VALUE, "mode": "bad"}, "mode"),
        (
            {"name": "x", "value": {"repeat": 1, "events": [], "extra": 1}, "mode": "count"},
            "exactly",
        ),
        (
            {
                "name": "x",
                "value": {"repeat": 1, "events": [{"hid_usage": 4, "down": 1, "delay_ms": 10}]},
                "mode": "count",
            },
            "boolean",
        ),
        ({"name": "x", "value": VALUE, "mode": "count", "revision": 1}, "requires"),
    ],
)
def test_strict_fields(tmp_path, payload, message):
    controller = server.Controller(tmp_path / "backups")
    with pytest.raises(ValueError, match=message):
        controller.call("macro_library_save", payload)


def test_corrupt_entry_is_actionable_and_failed_update_preserves_old(tmp_path, monkeypatch):
    path = tmp_path / "library"
    library = macro_library.MacroLibrary(path)
    entry = library.save("Alpha", VALUE, "count")
    (path / ("f" * 32 + ".json")).write_text("not json")
    with pytest.raises(ValueError, match="invalid macro library entry"):
        library.list()
    valid_path = path / f"{entry['id']}.json"
    before = valid_path.read_bytes()
    original = profiles.save

    def fail(path_arg, value, **kwargs):
        if kwargs.get("overwrite"):
            raise OSError("disk full")
        return original(path_arg, value, **kwargs)

    monkeypatch.setattr(macro_library.profiles, "save", fail)
    with pytest.raises(OSError, match="disk full"):
        library.save("Changed", VALUE, "toggle", entry["id"], 1)
    assert valid_path.read_bytes() == before


def test_http_routes_offline_and_auth(tmp_path):
    controller = server.Controller(tmp_path / "backups")
    with server.ControlServer(controller, web_root=tmp_path, token="secret") as instance:
        thread = threading.Thread(target=instance.serve_forever, daemon=True)
        thread.start()
        try:

            def request(path, method="GET", body=None, token="secret"):
                conn = http.client.HTTPConnection("127.0.0.1", instance.server_port, timeout=3)
                headers = {"X-Epomaker-Token": token, "Content-Type": "application/json"}
                conn.request(
                    method,
                    path,
                    body=json.dumps(body) if body is not None else None,
                    headers=headers,
                )
                response = conn.getresponse()
                result = response.status, json.loads(response.read())
                conn.close()
                return result

            assert request("/api/macro_library") == (200, {"entries": []})
            assert request("/api/macro_library", token="wrong")[0] == 403
            status, entry = request(
                "/api/macro_library_save", "POST", {"name": "A", "value": VALUE, "mode": "held"}
            )
            assert status == 200 and entry["mode"] == "held"
            assert request(
                "/api/macro_library_delete", "POST", {"id": entry["id"], "revision": 1}
            ) == (200, {"ok": True})
        finally:
            instance.shutdown()
            thread.join()
