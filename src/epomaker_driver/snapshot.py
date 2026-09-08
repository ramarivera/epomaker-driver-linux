"""Versioned keyboard configuration snapshots; validate all fields before restoration."""

from . import codec, profiles
from .errors import ProtocolError, UnsupportedDevice
from .models import model_by_id, validate_sleep_times

LIMITATIONS = ["screen pixels and unreferenced macro slots are not included"]


def macro_slots(matrices):
    return sorted({data[i + 2] for data in matrices for i in range(0, 512, 4) if data[i] == 9})


def capture(keyboard, *, extra_macro_slots=()):
    def operation():
        identity = keyboard.identify()
        keyboard._supported()
        if identity["device_id"] not in (2895, 3059, 3223):
            raise UnsupportedDevice("Snapshots currently support Glyph, RT85 and RT75")
        rt85 = identity["device_id"] == 2895
        matrices = [keyboard.read_matrix(p) for p in range(keyboard.model["layer"])]
        fn = {
            name: keyboard.read_matrix(fn=True, os_mode=mode)
            for name, mode in (("win", 0), ("mac", 1))
        }
        slots = sorted(set(macro_slots(matrices + list(fn.values()))) | set(extra_macro_slots))
        macros = {str(slot): keyboard.read_macro(slot).hex() for slot in slots}
        status = keyboard.status()
        return {
            "schema_version": 3 if identity["device_id"] == 3059 else 4,
            "identity": identity,
            "matrices": [m.hex() for m in matrices],
            "fn": {k: v.hex() for k, v in fn.items()},
            "macros": macros,
            "pictures": [keyboard.read_picture(i).hex() for i in range(5)],
            "light": keyboard.get_light(),
            "side_light": None if identity["device_id"] == 3223 else keyboard.get_light(side=True),
            "sleep": keyboard.get_sleep(),
            "profile": status["profile"],
            "debounce": None if rt85 else status["debounce"],
            "options": keyboard.get_options(),
            "auto_os": keyboard.get_auto_os(),
            "limitations": LIMITATIONS.copy(),
        }

    return keyboard.transport.transaction(operation)


def validate(value):
    """Return decoded bytes and reject incomplete/incompatible snapshots without I/O."""
    try:
        if type(value["schema_version"]) is not int or value["schema_version"] not in (2, 3, 4):
            raise ValueError("restoration requires a version 2, 3 or 4 snapshot")
        model_id = value["identity"]["device_id"]
        if type(model_id) is not int or model_id not in (2895, 3059, 3223):
            raise ValueError("snapshot model must be Glyph ID 3059, RT85 ID 2895 or RT75 ID 3223")
        if value["schema_version"] < 4 and model_id != 3059:
            raise ValueError("version 2 and 3 snapshots are only for Glyph ID 3059")
        count = model_by_id(model_id)["layer"]
        matrices = [bytes.fromhex(m) for m in value["matrices"]]
        fn = {name: bytes.fromhex(value["fn"][name]) for name in ("win", "mac")}
        if len(matrices) != count or any(len(m) != 512 for m in matrices + list(fn.values())):
            raise ValueError("snapshot must contain every model profile as a 512-byte matrix")
        macros = {}
        for key, raw in value["macros"].items():
            slot = codec.bounded(int(key), 255, "macro slot")
            if str(slot) != key:
                raise ValueError("macro slot must be canonical decimal")
            data = bytes.fromhex(raw)
            if len(data) != 256:
                raise ValueError("macro must be 256 bytes")
            macros[slot] = data
        if not set(macro_slots(matrices + list(fn.values()))) <= set(macros):
            raise ValueError("snapshot omits a referenced macro")
        pictures = []
        if value["schema_version"] >= 3:
            pictures = [bytes.fromhex(raw) for raw in value["pictures"]]
            if len(pictures) != 5 or any(len(p) != 378 for p in pictures):
                raise ValueError("snapshot requires five 378-byte RGB pictures")
        settings = []
        for key, opcode in (("light", 7), ("side_light", 8), ("options", 9)):
            if model_id == 3223 and key == "side_light":
                if value[key] is not None:
                    raise ValueError("RT75 snapshots must leave side_light null")
                continue
            raw = bytes(value[key]["raw"])
            if len(raw) != 64 or raw[0] != opcode + 128:
                raise ValueError(f"invalid {key} response data")
            if model_id == 2895 and key == "side_light":
                if raw[1] not in range(5) or raw[2] > (4 if raw[1] == 4 else 3):
                    raise ValueError("RT85 side lighting mode or speed is unsupported")
            payload = bytes([opcode]) + raw[1 : 8 if opcode != 9 else 7]
            settings.append(codec.packet(payload, 7 if opcode == 9 else 8))
        sleep = value["sleep"]
        times = [sleep[k] for k in ("bluetooth", "dongle", "deep_bluetooth", "deep_dongle")]
        sleep_command = codec.sleep_times(*times)
        validate_sleep_times(model_id, times)
        codec.bounded(value["profile"], count - 1, "profile")
        if model_id == 2895:
            if value["debounce"] is not None:
                raise ValueError("RT85 snapshots must leave debounce null")
        else:
            codec.bounded(value["debounce"], 255, "debounce")
        if type(value["auto_os"]) is not bool:
            raise ValueError("auto_os must be boolean")
        return matrices, fn, macros, settings, sleep_command, pictures
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("snapshot has missing or malformed fields") from error


def restore(keyboard, value, backup_path):
    matrices, fn, macros, settings, sleep_command, pictures = validate(value)

    def operation():
        identity = keyboard.identify()
        if identity["device_id"] != value["identity"]["device_id"]:
            raise ValueError("snapshot model does not match the connected keyboard")
        # Save current configuration before the first write; no-clobber is intentional.
        current = capture(keyboard, extra_macro_slots=macros)
        validate(current)
        profiles.save(backup_path, current)
        try:
            for slot, data in macros.items():
                keyboard.write_macro(slot, data)
            for index, matrix in enumerate(matrices):
                keyboard.write_matrix(matrix, index)
            for mode, name in enumerate(("win", "mac")):
                keyboard.write_fn_matrix(fn[name], mode)
            for index, colors in enumerate(pictures):
                keyboard.write_picture(colors, index)
            keyboard._write(settings + [sleep_command])
            keys = (
                ("light", "options")
                if value["identity"]["device_id"] == 3223
                else ("light", "side_light", "options")
            )
            for key, command in zip(keys, settings, strict=True):
                read = (
                    keyboard.get_options()
                    if key == "options"
                    else keyboard.get_light(side=key == "side_light")
                )
                end = 7 if key == "options" else 8
                if bytes(read["raw"][1:end]) != command[1:end]:
                    raise ProtocolError(f"{key} readback differs")
            if keyboard.get_sleep() != value["sleep"]:
                raise ProtocolError("sleep readback differs")
            if value["debounce"] is not None:
                keyboard.set_debounce(value["debounce"])
            keyboard.set_auto_os(value["auto_os"])
            keyboard.set_profile(value["profile"])
        except Exception as error:
            raise ProtocolError(
                f"restore stopped; device may be partially changed; "
                f"previous configuration is saved at {backup_path}: {error}"
            ) from error
        return {
            "restored": True,
            "previous_configuration": str(backup_path),
            "limitations": LIMITATIONS.copy()
            + ([] if pictures else ["version 2 snapshot leaves custom RGB pictures unchanged"]),
        }

    return keyboard.transport.transaction(operation)


def factory_reset(keyboard, backup_path):
    """Save every macro slot and current settings before sending the vendor reset."""

    def operation():
        keyboard._check_commands([codec.packet([1])])
        current = capture(keyboard, extra_macro_slots=range(256))
        current["limitations"] = ["screen pixels are not included"]
        validate(current)
        profiles.save(backup_path, current)
        try:
            keyboard._supported()
            keyboard.transport.send(codec.packet([1]))
            keyboard.transport.sleep(2)
        except Exception as error:
            raise ProtocolError(
                f"reset outcome is unknown; recovery snapshot is saved at {backup_path}: {error}"
            ) from error
        finally:
            keyboard.identity = None
            keyboard.model = None
        return {
            "reset_sent": True,
            "factory_defaults_verified": False,
            "previous_configuration": str(backup_path),
            "limitations": current["limitations"],
        }

    return keyboard.transport.transaction(operation)
