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
    names = {3059: "glyph", 2895: "rt85"}
    if device_id not in names:
        raise UnsupportedDevice("No migrated default matrices for this model")
    matrices = data_file(f"{names[device_id]}-matrices.json")
    if layer not in matrices:
        raise ValueError("unknown default matrix")
    return bytes(matrices[layer])
