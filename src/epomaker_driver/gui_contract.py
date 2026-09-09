"""GUI choices matching implemented backend gates; see docs/control-interface.md."""

from . import codec
from .errors import UnsupportedDevice
from .models import (
    HE_SLEEP_IDS,
    RY5088_EI_SIDE_IDS,
    RY5088_IDS,
    RY5088_SIDE_IDS,
    RY6602_IDS,
    RY6602_SCREEN_IDS,
    RY6602_SIDE_IDS,
    data_file,
    default_matrix,
    display_spec,
    model_by_id,
)

LEGACY_IDS = (1379, 1723)
HE_IDS = (*RY5088_IDS, 3727, 3759)
MODERN_IDS = (2895, 3059, 3223, 3152, *RY6602_IDS)
GUI_IDS = (*LEGACY_IDS, *HE_IDS, *MODERN_IDS)


def _matrices(model_id):
    names = ("defaultMatrix", "defaultFnMatrix", "defaultFnMacMatrix")
    if model_id in HE_IDS:
        rows = data_file("he60-matrices.json")[str(model_id)]
        return [list(rows.get(name, [0] * 512)) for name in names]
    if model_id in MODERN_IDS:
        return [list(default_matrix(model_id, name)) for name in names]
    # Legacy defaults have not been extracted. Connected reads populate this slot grid.
    return [[0] * 512 for _ in names]


def _lighting(model_id, *, side=False):
    source = dict(codec.SIDE_MODES if side else codec.LIGHT_MODES)
    if side:
        if model_id in RY5088_EI_SIDE_IDS:
            allowed = ("off", "solid", "neon", "wave")
        elif model_id == 2895:
            allowed = ("off", "solid", "breathing", "neon", "wave")
        elif model_id in RY6602_SIDE_IDS:
            allowed = ("off", "breathing", "wave", "snake")
        else:
            allowed = source
        source = {name: code for name, code in source.items() if name in allowed}
    elif model_id not in (2895, 3059):
        source.pop("off", None)
    result = {}
    for name, code in source.items():
        speed = 3 if side else 4
        if side and (model_id in RY5088_EI_SIDE_IDS or (model_id == 2895 and name == "wave")):
            speed = 4
        if name in ("off", "solid", "picture", "music", "screen"):
            speed = 0
        option = (
            0
            if side
            else {
                "wave": 3,
                "snake": 1,
                "kaleidoscope": 1,
                "line-wave": 1,
                "circle-wave": 1,
                "music": 2,
                "picture": 2 if model_id in (*LEGACY_IDS, 3727) else 4,
            }.get(name, 0)
        )
        color = name not in ("off", "neon", "picture", "screen")
        result[name] = {
            "code": code,
            "speed_max": speed,
            "option_max": option,
            "rgb": color,
            "rainbow": color,
            "brightness": name != "off",
        }
    return result


def _sleep(model_id):
    if model_id in HE_IDS:
        if model_id not in HE_SLEEP_IDS:
            return {}
        if model_id == 3759:
            return {key: {"min": 60, "max": 3600} for key in ("bt", "dongle", "deep_bt")}
        if model_id == 3883:
            return {key: {"min": 0, "max": 65535} for key in ("bt", "dongle", "deep_bt")}
        if model_id == 3417:
            return {key: {"min": 0, "max": 64800} for key in ("bt", "dongle")}
        if model_id not in (3365, 3518, 3613, 4071):
            return {
                key: {"min": 10 if key == "deep_bt" else 0, "max": 64800}
                for key in ("bt", "dongle", "deep_bt")
            }
    other = model_by_id(model_id)["other"]
    result = {}
    for key, connection, kind in (
        ("bt", "sleepBT", "sleep"),
        ("dongle", "sleep24", "sleep"),
        ("deep_bt", "sleepBT", "deep"),
        ("deep_dongle", "sleep24", "deep"),
    ):
        limits = other[connection].get(kind)
        if limits is not None:
            result[key] = {"min": limits["min"], "max": limits["max"]}
    return result


def ui_descriptor(model_id, *, status=None):
    if model_id not in GUI_IDS:
        raise UnsupportedDevice("no graphical keyboard backend for this model")
    model = model_by_id(model_id)
    legacy, magnetic = model_id in LEGACY_IDS, model_id in HE_IDS
    profiles = 2 if model_id in (3727, 3759) else model["layer"]
    fn_modes = (
        [{"label": "Fn", "os_mode": 0}]
        if legacy
        else [
            {"label": label, "os_mode": mode}
            for name, label, mode in (("win", "Fn Windows", 0), ("mac", "Fn Mac", 1))
            if model["fnSysLayer"].get(name)
        ]
    )
    display_ids = (2376, 2895, 3059, 3223, 3152, *LEGACY_IDS, *RY6602_SCREEN_IDS)
    display = display_spec(model_id) if model_id in display_ids else None
    side = model_id in (2895, 3059, *RY6602_SIDE_IDS, *RY5088_SIDE_IDS)
    sleep = _sleep(model_id)
    controls = ["keymap", "lighting", "macros", "settings", "backups", "auto_os"]
    if not legacy:
        controls.append("options")
    if display:
        controls.append("display")
    if model_id in (2376, 2895, 3059, 3223, 3152, *LEGACY_IDS):
        controls.append("clock")
    if model_id in (2376, 2895, 3059, 3223, 3152, 1379):
        controls.append("display_language_toggle")
    if model_id in (3059, 3223, 3152, *LEGACY_IDS):
        controls.append("system_info")
    if legacy or model_id == 3727 or (model_id in MODERN_IDS and model_id != 2895):
        controls.append("debounce")
    if sleep:
        controls.append("sleep")
    if side:
        controls.append("side_lighting")
    schemas = (
        [7]
        if magnetic
        else [6]
        if legacy
        else [5]
        if model_id in RY6602_IDS
        else [2, 3]
        if model_id == 3059
        else [4]
    )
    limitations = ["Screen pixels, clock, and display language are not captured."]
    if magnetic:
        limitations.append("Persistent sensor calibration and firmware are not captured.")
    else:
        limitations.append("Unreferenced macro slots are not captured.")
    return {
        "profiles": profiles,
        "fn_modes": fn_modes,
        "submodes": 4 if magnetic else 1,
        "matrix_slots": 128,
        "macro_slots": 256,
        "picture_banks": 1 if legacy else 3 if model_id == 3727 else 5,
        "picture_slots": 128 if legacy else 126,
        "controls": controls,
        "display": display,
        "backup_schemas": schemas,
        "backup_limitations": limitations,
        "sleep_fields": list(sleep),
        "sleep_limits": sleep,
        "light_modes": _lighting(model_id),
        "side_modes": _lighting(model_id, side=True) if side else {},
    }


def catalog_contract(model_id):
    ui = ui_descriptor(model_id)
    if model_id == 3059:
        layout = data_file("glyph-key-layout.json")
    else:
        # Explicit slot numbers avoid inferring physical positions from duplicate HID actions.
        layout = {
            "width": 800,
            "height": 400,
            "layout": {
                f"slot-{slot}": {
                    "slot": slot,
                    "x": slot % 16 * 50,
                    "y": slot // 16 * 50,
                    "width": 46,
                    "height": 46,
                    "displayText": [str(slot)],
                }
                for slot in range(128)
            },
        }
    return {"ui": ui, "matrices": _matrices(model_id), "layout": layout}
