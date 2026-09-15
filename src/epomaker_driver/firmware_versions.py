"""Compare vendor firmware version tokens with offline component metadata."""

from __future__ import annotations

import re

COMPONENTS = ("usb", "rf", "oled", "flash", "mled", "nordic")
MARKERS = ("nordicv", "mledv", "oledv", "flashv", "rfv", "usbv")


def _version(token: str, marker: str, *, require_marker: bool) -> int:
    if (require_marker and token.count(marker) != 1) or token.count(marker) > 1:
        raise ValueError(f"ambiguous firmware token: {token}")
    if any(other in token for other in MARKERS if other != marker):
        raise ValueError(f"ambiguous firmware token: {token}")
    digits = re.findall(r"[0-9]+", token)
    if not digits:
        raise ValueError(f"firmware token has no version digits: {token}")
    value = int("".join(digits), 16)
    if value > 65535:
        raise ValueError(f"firmware version is out of range: {token}")
    return value


def analyze(version_str: str, current: dict, components: dict) -> dict:
    """Return offline firmware candidate comparisons; never performs I/O."""
    if not isinstance(version_str, str) or not version_str or len(version_str) > 256:
        raise ValueError("version string must be nonempty and at most 256 characters")
    if not isinstance(current, dict) or set(current) - set(COMPONENTS):
        raise ValueError("current contains unsupported component keys")
    for name, value in current.items():
        if value is not None and (type(value) is not int or not 0 <= value <= 65535):
            raise ValueError(f"current {name} version must be null or an integer from 0 to 65535")
    if not isinstance(components, dict):
        raise ValueError("components must be an object")
    unknown = set(components) - {"main", *COMPONENTS[1:]}
    if unknown:
        raise ValueError(f"unknown firmware components: {list(map(str, unknown))}")
    if not components.get("main"):
        raise ValueError("main firmware image is required")
    tokens = [token for token in version_str.split("_") if token]
    if not tokens:
        raise ValueError("version string contains no tokens")
    parsed = []
    seen = set()
    for index, token in enumerate(tokens):
        marker = "usbv" if index == 0 else next((item for item in MARKERS if item in token), None)
        if marker is None:
            raise ValueError(f"unknown firmware token: {token}")
        component = "usb" if marker == "usbv" else marker[:-1]
        if component in seen:
            raise ValueError(f"duplicate firmware component token: {component}")
        seen.add(component)
        observed = _version(token, marker, require_marker=index > 0)
        image_key = "main" if component == "usb" else component
        available = bool(components.get(image_key))
        reason = "available"
        candidate = False
        if not available:
            reason = "missing-image"
        elif component in ("mled", "nordic"):
            reason = "unsupported-dispatch"
        elif current.get(component) in (None, 0):
            reason = "unknown-current"
        elif observed <= current.get(component):
            reason = "not-newer"
        else:
            candidate = True
        parsed.append(
            {
                "component": component,
                "observed": observed,
                "current": current.get(component),
                "candidate": candidate,
                "reason": reason,
            }
        )
    return {
        "version": version_str,
        "candidates": parsed,
        "write_ready": False,
        "authenticity_verified": False,
        "model_applicability": "unverified",
    }
