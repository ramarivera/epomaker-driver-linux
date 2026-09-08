"""Device facts and implementation availability; catalog presence is not support."""

from __future__ import annotations

import json
from importlib.resources import files

from .errors import UnsupportedDevice

# Shared modern magnetic protocol; gates: docs/ry5088-he68.md and docs/ry5088-he60.md.
RY5088_PRODUCTS = {
    0x5029: (3662, 3664, 3746, 2762, 2883, 2465),
    0x502D: (2586, 2870),
    0x5030: (3691, 3692, 3703, 2761, 2959),
}
RY5088_IDS = tuple(mid for ids in RY5088_PRODUCTS.values() for mid in ids)
RY5088_SWITCH_IDS = tuple(mid for mid in RY5088_IDS if mid != 3662)
RY5088_SIDE_IDS = (2586, 2870, 3703, 2959)
# Wireless-capable models are currently enabled over USB only; docs/ry5088-wireless.md.
RY5088_WIRELESS_IDS = (3692, 3703, 2761, 2959)
HE_RF_IDS = (*RY5088_WIRELESS_IDS, 3759)
HE_SLEEP_IDS = HE_RF_IDS

# Explicitly migrated RY6602 models; see docs/ry6602.md.
RY6602_IDS = (3858, 3633, 3673, 3573, 3674)
RY6602_SIDE_IDS = (3673, 3573, 3674)
RY6602_SCREEN_IDS = (3858, 3673, 3674)
RT100_PRO_IDS = (3152,)


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
    names = {
        3059: "glyph",
        2895: "rt85",
        3223: "rt75",
        3152: "rt100pro",
        **{mid: f"ry6602-{mid}" for mid in RY6602_IDS},
    }
    if device_id not in names:
        raise UnsupportedDevice("No migrated default matrices for this model")
    matrices = data_file(f"{names[device_id]}-matrices.json")
    if layer not in matrices:
        raise ValueError("unknown default matrix")
    return bytes(matrices[layer])


def display_spec(device_id: int) -> dict:
    """Migrated RGB display limits, derived from the installer catalog."""
    if device_id not in (2895, 3059, 3223, 1379, 1723, *RT100_PRO_IDS, *RY6602_SCREEN_IDS):
        raise UnsupportedDevice("No migrated display protocol for this model")
    screen = model_by_id(device_id)["other"]["screen"]
    size = screen["size"]
    width, height = size["w"], size["h"]
    banks = len(screen.get("layer", ["1", "2", "3", "4", "5"]))
    # Vendor rounds to the next block even when exactly aligned; docs/display.md.
    pixel_bytes = 3 if screen["mode"] == "24" else 2
    block_bytes = (width * height * pixel_bytes // 4096 + 1) * 4096
    # The vendor drawing board defaults an omitted memorySize to 7 MiB.
    memory_size = size.get("memorySize")
    if memory_size is None:
        if device_id not in (1723, *RT100_PRO_IDS):
            raise UnsupportedDevice("Display memory is missing from the model catalog")
        memory_size = 7
    maximum = min(255, (memory_size * 1024 * 1024 - 4096) // block_bytes - banks)
    if device_id == 3674:
        maximum = size["memorySize"] // (width * height * pixel_bytes)
    return {
        "width": width,
        "height": height,
        "banks": banks,
        "max_frames": maximum,
        "pixel_bytes": pixel_bytes,
    }


def validate_sleep_times(model_id: int, values):
    """Apply the same catalog limits to direct writes and snapshot restoration."""
    from .codec import bounded

    model = model_by_id(model_id)
    fields = (("sleepBT", "sleep"), ("sleep24", "sleep"), ("sleepBT", "deep"), ("sleep24", "deep"))
    for value, (connection, kind) in zip(values, fields, strict=True):
        limits = model["other"][connection].get(kind)
        if limits is None:
            if value is not None:
                raise ValueError(f"{connection} {kind} is not exposed by this model; omit it")
            continue
        bounded(value, limits["max"], "sleep seconds")
        if value < limits["min"]:
            raise ValueError(f"{connection} {kind} must be at least {limits['min']} seconds")


def light_encoding(model_id: int):
    """Normal/rainbow flags and readback palette; installer overrides: docs/ry6602.md."""
    from .codec import DEFAULT_LIGHT_PALETTE

    palettes = {
        3573: (16711680, 65280, 255, 16733440, 7799039, 16776960, 16777215),
        3674: (16711680, 65280, 255, 16776960, 16732250, 65535, 16777215),
    }
    if model_id in palettes:
        return 8, 7, palettes[model_id]
    return 7, 8, DEFAULT_LIGHT_PALETTE
