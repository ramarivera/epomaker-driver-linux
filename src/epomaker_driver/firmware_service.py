"""Read-only vendor metadata query; see docs/releases/glyph-firmware-service-audit.md."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import DriverError

ENDPOINT = "https://api2.rongyuan.tech:3816/api/v2/get_fw_version"
MAX_RESPONSE = 65536


class FirmwareServiceError(DriverError):
    """Metadata could not be obtained; this is not evidence of no updates."""


def fetch_metadata():
    """Query model 3059 only. No credentials, image download, or device access."""
    request = Request(
        ENDPOINT,
        data=b'{"dev_id":3059}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=8) as response:
            raw = response.read(MAX_RESPONSE + 1)
    except HTTPError as error:
        with error:
            body = error.read(MAX_RESPONSE + 1)
        missing = body.strip() == b"Record not found"
        detail = ": Record not found for Glyph model 3059" if missing else ""
        raise FirmwareServiceError(
            f"firmware metadata lookup failed (HTTP {error.code}){detail}; update availability is unknown"
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        raise FirmwareServiceError(
            "firmware metadata service is unreachable; try again later"
        ) from error
    if len(raw) > MAX_RESPONSE:
        raise FirmwareServiceError("firmware metadata response exceeds size limit")
    try:
        envelope = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise FirmwareServiceError("firmware metadata response is not valid JSON") from error
    if not isinstance(envelope, dict) or type(envelope.get("code")) is not int:
        raise FirmwareServiceError("firmware metadata response has an invalid status")
    if envelope["code"] != 0:
        raise FirmwareServiceError("firmware metadata service rejected the lookup")
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise FirmwareServiceError("firmware metadata response has no record")
    for key, limit in (("version_str", 256), ("file_path", 2048)):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise FirmwareServiceError(f"firmware metadata has an invalid {key}")
    return {
        "requested_model_id": 3059,
        "version_str": data["version_str"],
        "file_path": data["file_path"],
        "source": ENDPOINT,
        "write_ready": False,
        "authenticity_verified": False,
    }
