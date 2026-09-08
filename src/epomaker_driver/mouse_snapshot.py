"""Schema-8 raw snapshots and recovery for CH585 mice."""

from __future__ import annotations

import sys

from . import codec, mouse_codec, profiles
from .errors import ProtocolError, UnsupportedDevice
from .models import model_by_id
from .mouse import PRODUCTS, setting_options_for

SCHEMA_VERSION = 8
PROFILE_COUNT = 8
MACRO_COUNT = 50
_MODEL_IDS = PRODUCTS[0x503A] + PRODUCTS[0x5043]


def _hex(value, size, name):
    if type(value) is not str:
        raise ValueError(f"{name} must be hexadecimal text")
    try:
        raw = bytes.fromhex(value)
    except ValueError as error:
        raise ValueError(f"{name} must be hexadecimal text") from error
    if len(raw) != size:
        raise ValueError(f"{name} must contain exactly {size} bytes")
    return raw


def _setting_names(model_id, usb_version):
    options = setting_options_for(model_by_id(model_id), usb_version)
    names = ["debounce", "scroll_up_time", "sleep_24", "line_repair", "wave_repair"]
    if options["sleep_bt"]:
        names.append("sleep_bt")
    if options["lod_mm"]:
        names.append("lod")
    if options["low_latency"]:
        names.append("low_latency")
    return tuple(names)


def _identity(value):
    if type(value) is not dict or set(value) != {"device_id", "usb_version"}:
        raise ValueError("snapshot identity must contain exactly device_id and usb_version")
    model_id, usb = value["device_id"], value["usb_version"]
    if type(model_id) is not int or model_id not in _MODEL_IDS:
        raise ValueError("snapshot device ID is not a supported CH585 mouse")
    if usb is not None and (type(usb) is not int or not 0 <= usb <= 0xFFFF):
        raise ValueError("snapshot USB version must be a uint16 or null")
    return model_id, usb


def _canonical_map(value, count, size, name):
    if type(value) is not dict or set(value) != {str(i) for i in range(count)}:
        raise ValueError(f"{name} must contain canonical slots 0 through {count - 1}")
    return {int(key): _hex(value[key], size, f"{name} {key}") for key in value}


def _known_settings(model_id, usb):
    return set(_setting_names(model_id, usb)) | {"report_rate"}


def validate(value):
    """Validate and decode a schema-8 snapshot without device I/O."""
    if type(value) is not dict:
        raise ValueError("snapshot must be an object")
    required = {"schema_version", "identity", "profile", "profiles", "macros", "limitations"}
    if (
        set(value) != required
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 8
    ):
        raise ValueError("snapshot must contain exactly schema version 8 fields")
    model_id, usb = _identity(value["identity"])
    profile = codec.bounded(value["profile"], PROFILE_COUNT - 1, "profile")
    expected = _known_settings(model_id, usb)
    rows = value["profiles"]
    if type(rows) is not list or len(rows) != PROFILE_COUNT:
        raise ValueError("snapshot must contain eight profiles")
    decoded_rows = []
    for row in rows:
        if type(row) is not dict or set(row) != {"matrix", "dpi", "settings"}:
            raise ValueError("each profile must contain matrix, dpi and settings")
        matrix = _hex(row["matrix"], 64, "matrix")
        dpi = _hex(row["dpi"], 64, "DPI")
        if dpi[0] != 0x90:
            raise ValueError("DPI must be a 0x90 response")
        settings = row["settings"]
        if type(settings) is not dict or set(settings) != expected:
            raise ValueError("profile settings do not match model and USB version")
        decoded = {}
        for name in expected:
            item = settings[name]
            if name == "report_rate":
                if type(item) is not int or not 0 <= item <= 255:
                    raise ValueError("report_rate must be a raw byte")
            elif mouse_codec.SETTINGS[name][4] == "bool":
                if type(item) is not bool:
                    raise ValueError(f"{name} must be boolean")
            else:
                width = mouse_codec.SETTINGS[name][2]
                if type(item) is not int or not 0 <= item <= (1 << (8 * width)) - 1:
                    raise ValueError(f"{name} must fit its wire width")
            decoded[name] = item
        decoded_rows.append({"matrix": matrix, "dpi": dpi, "settings": decoded})
    macros = _canonical_map(value["macros"], MACRO_COUNT, 256, "macro")
    limitations = value["limitations"]
    if type(limitations) is not list or any(type(item) is not str for item in limitations):
        raise ValueError("limitations must be a list of strings")
    return {
        "schema_version": 8,
        "identity": {"device_id": model_id, "usb_version": usb},
        "profile": profile,
        "profiles": decoded_rows,
        "macros": macros,
        "limitations": list(limitations),
    }


def _report_raw(mouse, profile):
    raw = mouse._query([0x88], 0x88)
    if len(raw) != 64:
        raise ProtocolError("report-rate response must be 64 bytes")
    return raw[1]


def _capture_body(mouse):
    identity = mouse.identify()
    model_id, usb = identity["device_id"], identity["usb_version"]
    expected_names = _setting_names(model_id, usb)
    names = []
    for name in expected_names:
        try:
            mouse._setting_supported(name)
        except UnsupportedDevice:
            continue
        names.append(name)
    if set(names) != set(expected_names):
        raise ProtocolError("mouse setting gates do not match the snapshot model metadata")
    original = mouse.get_profile()
    rows = []
    try:
        for profile in range(PROFILE_COUNT):
            if mouse.get_profile() != profile:
                mouse.set_profile(profile)
            if mouse.get_profile() != profile:
                raise ProtocolError("mouse profile changed during snapshot capture")
            matrix = bytes(mouse.read_matrix(profile))
            dpi = bytes(mouse.get_dpi(profile)["raw"])
            if len(matrix) != 64 or len(dpi) != 64 or dpi[0] != 0x90:
                raise ProtocolError("mouse profile response has an invalid length or opcode")
            rows.append(
                {
                    "matrix": matrix.hex(),
                    "dpi": dpi.hex(),
                    "settings": {name: mouse.get_setting(name) for name in names}
                    | {"report_rate": _report_raw(mouse, profile)},
                }
            )
            observed = mouse.identify()
            if (observed["device_id"], observed["usb_version"]) != (
                model_id,
                usb,
            ) or mouse.get_profile() != profile:
                raise ProtocolError("mouse identity or profile changed during snapshot capture")
        macros = {str(slot): mouse.read_macro(slot).hex() for slot in range(MACRO_COUNT)}
        final = mouse.identify()
        if (final["device_id"], final["usb_version"]) != (
            model_id,
            usb,
        ) or mouse.get_profile() != 7:
            raise ProtocolError("mouse identity or USB version changed during capture")
        return {
            "schema_version": 8,
            "identity": {"device_id": model_id, "usb_version": usb},
            "profile": original,
            "profiles": rows,
            "macros": macros,
            "limitations": [
                "vendor CH585 metadata exposes no mouse lighting layout",
                "firmware calibration state is not included",
                "wireless receiver and hidden vendor settings are not included",
                "hardware state was not verified by a physical-device run",
            ],
        }
    finally:
        active_error = sys.exc_info()[1]
        try:
            if mouse.get_profile() != original:
                mouse.set_profile(original)
        except BaseException as cleanup:
            if active_error is not None:
                raise ProtocolError(
                    f"mouse capture failed: {active_error}; profile cleanup failed: {cleanup}"
                ) from active_error
            raise ProtocolError(f"mouse capture profile cleanup failed: {cleanup}") from cleanup


def capture(mouse):
    if mouse.transport.kind != "usb":
        raise UnsupportedDevice("CH585 snapshots require USB")

    def operation():
        snapshot = _capture_body(mouse)
        validate(snapshot)
        return snapshot

    return mouse.transport.transaction(operation)


def _raw_setting_command(name, value):
    _get, opcode, width, maximum, kind = mouse_codec.SETTINGS[name]
    if kind == "bool":
        if type(value) is not bool:
            raise ValueError(f"{name} must be boolean")
        number = int(value)
    else:
        width_limit = (1 << (8 * width)) - 1
        if type(value) is not int or not 0 <= value <= width_limit:
            raise ValueError(f"{name} is outside its wire width")
        number = value
    payload = [opcode, number] if width == 1 else [opcode, number & 255, number >> 8]
    return codec.packet(payload)


def _raw_dpi_command(raw, profile):
    if len(raw) != 64 or raw[0] != 0x90:
        raise ValueError("invalid captured DPI response")
    command = bytearray(raw)
    command[0] = 0x10
    command[1] = profile
    command[4:7] = bytes(3)
    return codec.packet(command)


def _equivalent(left, right):
    if left["identity"] != right["identity"] or left["profile"] != right["profile"]:
        return False
    if left["macros"] != right["macros"]:
        return False
    for a, b in zip(left["profiles"], right["profiles"], strict=True):
        if a["matrix"] != b["matrix"] or a["settings"] != b["settings"]:
            return False
        old, new = a["dpi"], b["dpi"]
        if old[2:4] != new[2:4] or old[8:] != new[8:]:
            return False
    return True


def _raw_rate_command(code):
    if type(code) is not int or not 0 <= code <= 255:
        raise ValueError("report_rate must be a raw byte")
    return codec.packet([0x08, code])


def restore(mouse, snapshot, backup_path):
    decoded = validate(snapshot)
    target_id = decoded["identity"]["device_id"]

    def operation():
        identity = mouse.identify()
        if (identity["device_id"], identity["usb_version"]) != (
            target_id,
            decoded["identity"]["usb_version"],
        ):
            raise ValueError("snapshot identity or USB version does not match the connected mouse")
        original_profile = mouse.get_profile()
        current = capture(mouse)
        current_decoded = validate(current)
        if current_decoded["identity"] != decoded["identity"]:
            raise ProtocolError("mouse identity or USB version changed before backup")
        profiles.save(backup_path, current)
        try:
            for profile, row in enumerate(decoded["profiles"]):
                if mouse.get_profile() != profile:
                    mouse.set_profile(profile)
                fresh = mouse.identify()
                if (fresh["device_id"], fresh["usb_version"]) != (
                    target_id,
                    decoded["identity"]["usb_version"],
                ) or mouse.get_profile() != profile:
                    raise ProtocolError("mouse identity or profile changed before restore write")
                mouse.write_matrix(profile, row["matrix"])
                if mouse.get_profile() != profile:
                    raise ProtocolError("mouse profile changed before DPI restore")
                old_dpi = bytes(mouse.get_dpi(profile)["raw"])
                wanted_dpi = row["dpi"]
                dpi_changed = old_dpi[2:4] != wanted_dpi[2:4] or old_dpi[8:] != wanted_dpi[8:]
                if dpi_changed:
                    dpi_command = _raw_dpi_command(row["dpi"], profile)
                    if mouse.get_profile() != profile:
                        raise ProtocolError("mouse profile changed before DPI restore")
                    mouse._write(dpi_command)
                    actual_dpi = bytes(mouse.get_dpi(profile)["raw"])
                    if actual_dpi[2:4] != dpi_command[2:4] or actual_dpi[8:] != dpi_command[8:]:
                        raise ProtocolError(f"profile {profile} DPI readback differs")
                for name, value in row["settings"].items():
                    if mouse.get_profile() != profile:
                        raise ProtocolError("mouse profile changed before scalar restore")
                    before = (
                        _report_raw(mouse, profile)
                        if name == "report_rate"
                        else mouse.get_setting(name)
                    )
                    if mouse.get_profile() != profile:
                        raise ProtocolError("mouse profile changed during scalar restore read")
                    if before == value:
                        continue
                    command = (
                        _raw_rate_command(value)
                        if name == "report_rate"
                        else _raw_setting_command(name, value)
                    )
                    mouse._write(command)
                    actual = (
                        _report_raw(mouse, profile)
                        if name == "report_rate"
                        else mouse.get_setting(name)
                    )
                    if actual != value:
                        raise ProtocolError(f"profile {profile} {name} readback differs")
            for slot, raw in decoded["macros"].items():
                mouse.write_macro(slot, raw)
            if mouse.get_profile() != decoded["profile"]:
                mouse.set_profile(decoded["profile"])
            final = validate(capture(mouse))
            if not _equivalent(final, decoded):
                raise ProtocolError("final mouse snapshot differs from requested configuration")
        except BaseException as error:
            try:
                if mouse.get_profile() != original_profile:
                    mouse.set_profile(original_profile)
            except BaseException as cleanup:
                raise ProtocolError(
                    f"mouse restore stopped; backup saved at {backup_path}; "
                    f"partial state may remain; profile cleanup failed: {cleanup}; original error: {error}"
                ) from error
            raise ProtocolError(
                f"mouse restore stopped; backup saved at {backup_path}; partial state may remain: {error}"
            ) from error
        return {
            "restored": True,
            "previous_configuration": str(backup_path),
            "profile": decoded["profile"],
        }

    return mouse.transport.transaction(operation)
