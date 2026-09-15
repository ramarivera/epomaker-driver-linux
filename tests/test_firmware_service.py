import io
import json
from urllib.error import HTTPError, URLError

import pytest

from epomaker_driver import cli
from epomaker_driver import firmware_service as service


def reply(value):
    return io.BytesIO(json.dumps(value).encode())


def test_success_request_contract_and_offline_cli_device_access(monkeypatch, capsys):
    seen = []

    def open_request(request, timeout):
        seen.append((request, timeout))
        return reply({"code": 0, "data": {"version_str": "v101", "file_path": "firmware/test.dat"}})

    monkeypatch.setattr(service, "urlopen", open_request)
    monkeypatch.setattr(cli, "select_device", lambda _: pytest.fail("metadata must not access HID"))
    assert cli.main(["firmware-metadata"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["requested_model_id"] == 3059
    assert result["write_ready"] is False
    assert result["authenticity_verified"] is False
    request, timeout = seen[0]
    assert request.full_url == service.ENDPOINT
    assert request.method == "POST"
    assert json.loads(request.data) == {"dev_id": 3059}
    assert request.header_items() == [("Content-type", "application/json")]
    assert timeout == 8


@pytest.mark.parametrize(
    "body,expected",
    [(b"Record not found", "Record not found"), (b"secret internal trace", "HTTP 500")],
)
def test_http_errors_do_not_mean_up_to_date(monkeypatch, capsys, body, expected):
    def fail(*args, **kwargs):
        raise HTTPError(service.ENDPOINT, 500, "Server error", {}, io.BytesIO(body))

    monkeypatch.setattr(service, "urlopen", fail)
    assert cli.main(["firmware-metadata"]) == 1
    err = capsys.readouterr().err
    assert expected in err
    assert "availability is unknown" in err
    assert "secret internal trace" not in err


@pytest.mark.parametrize("error", [URLError("failed"), TimeoutError(), OSError("network")])
def test_network_errors(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(service, "urlopen", fail)
    with pytest.raises(service.FirmwareServiceError, match="unreachable"):
        service.fetch_metadata()


@pytest.mark.parametrize(
    "envelope", [[], {}, {"code": False}, {"code": 1}, {"code": 0}, {"code": 0, "data": {}}]
)
def test_invalid_envelopes(monkeypatch, envelope):
    monkeypatch.setattr(service, "urlopen", lambda *a, **k: reply(envelope))
    with pytest.raises(service.FirmwareServiceError):
        service.fetch_metadata()


@pytest.mark.parametrize(
    "key,value",
    [
        ("version_str", ""),
        ("version_str", "a" * 257),
        ("file_path", None),
        ("file_path", " "),
        ("file_path", "a" * 2049),
    ],
)
def test_invalid_metadata_fields(monkeypatch, key, value):
    data = {"version_str": "v1", "file_path": "firmware/a"}
    data[key] = value
    monkeypatch.setattr(service, "urlopen", lambda *a, **k: reply({"code": 0, "data": data}))
    with pytest.raises(service.FirmwareServiceError, match=key):
        service.fetch_metadata()


@pytest.mark.parametrize("raw", [b"invalid", b"\xff", bytes(65537)])
def test_invalid_or_oversized_body(monkeypatch, raw):
    monkeypatch.setattr(service, "urlopen", lambda *a, **k: io.BytesIO(raw))
    with pytest.raises(service.FirmwareServiceError):
        service.fetch_metadata()
