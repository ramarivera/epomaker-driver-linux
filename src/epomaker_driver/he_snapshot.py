"""Schema-7 snapshots for the migrated HE keyboards."""

from __future__ import annotations

from . import codec
from .errors import ProtocolError, UnsupportedDevice
from .magnetic import READ_PAGES, top_dead_zone_supported
from .models import (
    HE_SLEEP_IDS,
    RY5088_IDS,
    RY5088_SIDE_IDS,
    RY5088_SWITCH_IDS,
    model_by_id,
)

MODEL_IDS = (*RY5088_IDS, 3727, 3759)
SCHEMA_VERSION = 7
_BASE_FIELDS = (0, 1, 2, 3, 4, 5, 6, 7, 9, 10)


def _hex(value, length, name):
    if not isinstance(value, str):
        raise ValueError(f"{name} must be hexadecimal text")
    try:
        raw = bytes.fromhex(value)
    except ValueError as error:
        raise ValueError(f"{name} must be hexadecimal text") from error
    if len(raw) != length:
        raise ValueError(f"{name} must contain exactly {length} bytes")
    return raw


def _versions(value):
    if not isinstance(value, dict) or set(value) != {"usb", "rf"}:
        raise ValueError("versions must contain usb and rf")
    for key in ("usb", "rf"):
        version = value[key]
        if version is not None and (type(version) is not int or not 0 <= version <= 0xFFFF):
            raise ValueError(f"{key} version must be a uint16 or null")
    return value["usb"], value["rf"]


def _field_requirements(model_id, versions):
    usb, rf = versions
    fields = list(_BASE_FIELDS)
    if top_dead_zone_supported(usb=usb, rf=rf):
        fields.append(251)
    if model_id in RY5088_SWITCH_IDS:
        fields.append(252)
    return tuple(fields)


def _model(value):
    if not isinstance(value, dict) or type(value.get("device_id")) is not int:
        raise ValueError("identity must contain a numeric device_id")
    model_id = value["device_id"]
    if model_id not in MODEL_IDS:
        raise ValueError("snapshot model is not an implemented HE keyboard")
    if value.get("is_boot") is not False:
        raise ValueError("snapshot identity must be a non-boot device")
    return model_id


def validate(value):
    """Validate and decode a schema-7 HE snapshot without performing I/O."""
    if not isinstance(value, dict):
        raise ValueError("snapshot must be a mapping")
    required = {
        "schema_version",
        "identity",
        "versions",
        "profile",
        "profiles",
        "fn",
        "macros",
        "pictures",
        "light",
        "side_light",
        "options",
        "auto_os",
        "sleep",
        "debounce",
        "limitations",
    }
    if (
        set(value) != required
        or type(value["schema_version"]) is not int
        or value["schema_version"] != SCHEMA_VERSION
    ):
        raise ValueError("schema-7 snapshot has missing or unexpected fields")
    model_id = _model(value["identity"])
    versions = _versions(value["versions"])
    count = model_by_id(model_id)["layer"]
    if type(value["profile"]) is not int or not 0 <= value["profile"] < count:
        raise ValueError("active profile is outside the model profile range")

    fields_expected = _field_requirements(model_id, versions)
    profiles = value["profiles"]
    if not isinstance(profiles, list) or len(profiles) != count:
        raise ValueError("snapshot must contain every model profile")
    decoded_profiles = []
    for profile in profiles:
        if not isinstance(profile, dict) or set(profile) != {"matrices", "fields"}:
            raise ValueError("profile snapshot has unexpected fields")
        matrices = profile["matrices"]
        if not isinstance(matrices, list) or len(matrices) != 4:
            raise ValueError("each HE profile requires four submode matrices")
        matrices_decoded = [_hex(raw, 512, "matrix") for raw in matrices]
        raw_fields = profile["fields"]
        if not isinstance(raw_fields, dict):
            raise ValueError("profile fields must be a mapping")
        try:
            field_keys = tuple(int(key) for key in raw_fields)
        except (TypeError, ValueError) as error:
            raise ValueError("field keys must be canonical decimal strings") from error
        if any(type(key) is not str or str(int(key)) != key for key in raw_fields):
            raise ValueError("field keys must be canonical decimal strings")
        if set(field_keys) != set(fields_expected):
            raise ValueError("profile fields do not match the model and firmware gates")
        fields_decoded = {
            field: _hex(raw_fields[str(field)], READ_PAGES[field] * 64, f"field {field}")
            for field in fields_expected
        }
        decoded_profiles.append({"matrices": matrices_decoded, "fields": fields_decoded})

    fn = value["fn"]
    fn_names = ["win"]
    if model_by_id(model_id).get("fnSysLayer", {}).get("mac"):
        fn_names.append("mac")
    if not isinstance(fn, dict) or set(fn) != set(fn_names):
        raise ValueError("Fn banks do not match model metadata")
    decoded_fn = {name: _hex(fn[name], 512, f"Fn {name}") for name in fn_names}

    macros = value["macros"]
    if not isinstance(macros, dict) or set(macros) != {str(slot) for slot in range(256)}:
        raise ValueError("HE snapshots must contain all 256 macro slots")
    decoded_macros = {int(slot): _hex(raw, 256, f"macro {slot}") for slot, raw in macros.items()}

    picture_count = 3 if model_id == 3727 else 5
    pictures = value["pictures"]
    if not isinstance(pictures, list) or len(pictures) != picture_count:
        raise ValueError("snapshot has the wrong number of picture banks")
    decoded_pictures = [_hex(raw, 378, "picture") for raw in pictures]

    light = _hex(value["light"], 64, "light")
    if light[0] != 0x87:
        raise ValueError("light must be an 0x87 response")
    side = value["side_light"]
    if model_id in RY5088_SIDE_IDS:
        if side is None:
            raise ValueError("side-light model requires side_light")
        side_decoded = _hex(side, 64, "side_light")
        if side_decoded[0] != 0x88:
            raise ValueError("side_light must be an 0x88 response")
    elif side is not None:
        raise ValueError("model has no side-light layout")
    else:
        side_decoded = None
    options = _hex(value["options"], 64, "options")
    if options[0] != 0x89:
        raise ValueError("options must be an 0x89 response")
    if type(value["auto_os"]) is not bool:
        raise ValueError("auto_os must be boolean")
    sleep = value["sleep"]
    if model_id in HE_SLEEP_IDS:
        sleep_decoded = _hex(sleep, 64, "sleep")
        if sleep_decoded[0] != 0x91:
            raise ValueError("sleep must be an 0x91 response")
    elif sleep is not None:
        raise ValueError("wired model must leave sleep null")
    else:
        sleep_decoded = None
    debounce = value["debounce"]
    if model_id == 3727:
        if type(debounce) is not int or not 1 <= debounce <= 10:
            raise ValueError("HE debounce must be an integer from 1 through 10")
    elif debounce is not None:
        raise ValueError("this model has no debounce control")
    limitations = value["limitations"]
    if not isinstance(limitations, list) or any(not isinstance(item, str) for item in limitations):
        raise ValueError("limitations must be a list of strings")
    return {
        "schema_version": SCHEMA_VERSION,
        "identity": dict(value["identity"]),
        "versions": {"usb": versions[0], "rf": versions[1]},
        "profile": value["profile"],
        "profiles": decoded_profiles,
        "fn": decoded_fn,
        "macros": decoded_macros,
        "pictures": decoded_pictures,
        "light": light,
        "side_light": side_decoded,
        "options": options,
        "auto_os": value["auto_os"],
        "sleep": sleep_decoded,
        "debounce": debounce,
        "limitations": list(limitations),
    }


def capture(keyboard):
    """Capture every HE configuration domain under one serialized transaction."""
    if keyboard.transport.kind != "usb":
        raise UnsupportedDevice("HE snapshots require a USB transport")

    def operation():
        identity = keyboard.identify()
        model_id = identity["device_id"]
        if model_id not in MODEL_IDS:
            raise UnsupportedDevice("model is not supported by HE schema 7")
        original = keyboard._query(codec.packet([0x84]), expected=0x84)[1]
        codec.bounded(original, keyboard._profile_max(), "active profile")
        profiles = []
        versions = None
        primary_error = None
        try:
            for profile in range(keyboard._profile_max() + 1):
                if keyboard._query(codec.packet([0x84]), expected=0x84)[1] != profile:
                    keyboard.set_profile(profile)
                magnetic = keyboard.get_magnetic()
                if keyboard.expected_id != model_id or magnetic["profile"] != profile:
                    raise ProtocolError(
                        "identity or active profile changed during HE snapshot capture"
                    )
                usb, rf = magnetic["versions"]["usb"], magnetic["versions"]["rf"]
                if versions is None:
                    versions = {"usb": usb, "rf": rf}
                elif versions != {"usb": usb, "rf": rf}:
                    raise ProtocolError("firmware versions changed during HE snapshot capture")
                required = _field_requirements(model_id, (usb, rf))
                fields = {
                    str(field): keyboard._read_field(field, READ_PAGES[field] * 64).hex()
                    for field in required
                }
                matrices = [keyboard.read_matrix(profile, mode=mode).hex() for mode in range(4)]
                if keyboard._query(codec.packet([0x84]), expected=0x84)[1] != profile:
                    raise ProtocolError("active profile changed during HE snapshot capture")
                profiles.append({"matrices": matrices, "fields": fields})
            if keyboard._query(codec.packet([0x84]), expected=0x84)[1] != original:
                keyboard.set_profile(original)
            fn_names = ["win"]
            if keyboard.model.get("fnSysLayer", {}).get("mac"):
                fn_names.append("mac")
            fn = {
                name: keyboard.read_matrix(fn=True, os_mode=0 if name == "win" else 1).hex()
                for name in fn_names
            }
            macros = {str(slot): keyboard.read_macro(slot).hex() for slot in range(256)}
            picture_count = 3 if model_id == 3727 else 5
            result = {
                "schema_version": SCHEMA_VERSION,
                "identity": identity,
                "versions": versions,
                "profile": original,
                "profiles": profiles,
                "fn": fn,
                "macros": macros,
                "pictures": [keyboard.read_picture(index).hex() for index in range(picture_count)],
                "light": bytes(keyboard.get_light()["raw"]).hex(),
                "side_light": (
                    bytes(keyboard.get_light(side=True)["raw"]).hex()
                    if model_id in RY5088_SIDE_IDS
                    else None
                ),
                "options": bytes(keyboard.get_options()["raw"]).hex(),
                "auto_os": keyboard.get_auto_os(),
                "sleep": (
                    bytes(keyboard._query(codec.packet([0x91]), expected=0x91)).hex()
                    if model_id in HE_SLEEP_IDS
                    else None
                ),
                "debounce": keyboard.status().get("debounce") if model_id == 3727 else None,
                "limitations": [
                    "firmware, screen pixels/clock/language, and persistent sensor calibration are not included; hardware restoration is unverified"
                ],
            }
            if keyboard._query(codec.packet([0x84]), expected=0x84)[1] != original:
                raise ProtocolError("active profile changed during global configuration capture")
            validate(result)
            return result
        except BaseException as error:
            primary_error = error
            raise
        finally:
            try:
                if keyboard._query(codec.packet([0x84]), expected=0x84)[1] != original:
                    keyboard.set_profile(original)
            except BaseException as error:
                raise ProtocolError(
                    f"failed to restore active profile {original}: {error}; original failure: {primary_error!r}"
                ) from error

    return keyboard.transport.transaction(operation)
