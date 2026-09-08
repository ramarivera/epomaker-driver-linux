"""Device facts and implementation availability; catalog presence is not support."""

from __future__ import annotations

import json
from importlib.resources import files

from .errors import UnsupportedDevice


def data_file(name: str):
    return json.loads(files("epomaker_driver").joinpath("data", name).read_text())


def catalog() -> list[dict]:
    return data_file("models.json")


def model_by_id(device_id: int) -> dict:
    for model in catalog():
        if model["id"] == device_id:
            return model
    raise UnsupportedDevice(f"Unknown internal device ID {device_id}")


def glyph_matrix(layer="defaultMatrix") -> bytes:
    return default_matrix(3059, layer)


def default_matrix(device_id: int, layer="defaultMatrix") -> bytes:
    names = {3059: "glyph", 2895: "rt85", 3223: "rt75"}
    if device_id not in names:
        raise UnsupportedDevice("No migrated default matrices for this model")
    matrices = data_file(f"{names[device_id]}-matrices.json")
    if layer not in matrices:
        raise ValueError("unknown default matrix")
    return bytes(matrices[layer])


def display_spec(device_id: int) -> dict:
    """Migrated RGB565 display limits, derived from the installer catalog."""
    if device_id not in (2895, 3059, 3223):
        raise UnsupportedDevice("No migrated display protocol for this model")
    screen = model_by_id(device_id)["other"]["screen"]
    size = screen["size"]
    width, height = size["w"], size["h"]
    banks = len(screen.get("layer", ["1", "2", "3", "4", "5"]))
    # Vendor rounds to the next block even when exactly aligned; docs/display.md.
    block_bytes = (width * height * 2 // 4096 + 1) * 4096
    return {
        "width": width,
        "height": height,
        "banks": banks,
        "max_frames": (size["memorySize"] * 1024 * 1024 - 4096) // block_bytes - banks,
    }


def validate_sleep_times(model_id: int, values):
    """Apply the same catalog limits to direct writes and snapshot restoration."""
    from .codec import bounded

    model = model_by_id(model_id)
    fields = (("sleepBT", "sleep"), ("sleep24", "sleep"), ("sleepBT", "deep"), ("sleep24", "deep"))
    for value, (connection, kind) in zip(values, fields, strict=True):
        limits = model["other"][connection][kind]
        bounded(value, limits["max"], "sleep seconds")
        if value < limits["min"]:
            raise ValueError(f"{connection} {kind} must be at least {limits['min']} seconds")
