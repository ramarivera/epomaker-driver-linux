"""Versioned Glyph configuration snapshots; validate all fields before restoration."""

from . import codec, profiles
from .errors import ProtocolError

LIMITATIONS = ["screen pixels and unreferenced macro slots are not included"]


def macro_slots(matrices):
    return sorted({data[i + 2] for data in matrices for i in range(0, 512, 4) if data[i] == 9})


def capture(keyboard, *, extra_macro_slots=()):
    def operation():
        identity = keyboard.identify()
        matrices = [keyboard.read_matrix(p) for p in range(3)]
        fn = {
            name: keyboard.read_matrix(fn=True, os_mode=mode)
            for name, mode in (("win", 0), ("mac", 1))
        }
        slots = sorted(set(macro_slots(matrices + list(fn.values()))) | set(extra_macro_slots))
        macros = {str(slot): keyboard.read_macro(slot).hex() for slot in slots}
        status = keyboard.status()
        return {
            "schema_version": 3,
            "identity": identity,
            "matrices": [m.hex() for m in matrices],
            "fn": {k: v.hex() for k, v in fn.items()},
            "macros": macros,
            "pictures": [keyboard.read_picture(i).hex() for i in range(5)],
            "light": keyboard.get_light(),
            "side_light": keyboard.get_light(side=True),
            "sleep": keyboard.get_sleep(),
            "profile": status["profile"],
            "debounce": status["debounce"],
            "options": keyboard.get_options(),
            "auto_os": keyboard.get_auto_os(),
            "limitations": LIMITATIONS.copy(),
        }

    return keyboard.transport.transaction(operation)


def validate(value):
    """Return decoded bytes and reject incomplete/incompatible snapshots without I/O."""
    try:
        if type(value["schema_version"]) is not int or value["schema_version"] not in (2, 3):
            raise ValueError("restoration requires a version 2 or 3 snapshot")
        if value["identity"]["device_id"] != 3059:
            raise ValueError("snapshot is not for Glyph ID 3059")
        matrices = [bytes.fromhex(m) for m in value["matrices"]]
        fn = {name: bytes.fromhex(value["fn"][name]) for name in ("win", "mac")}
        if len(matrices) != 3 or any(len(m) != 512 for m in matrices + list(fn.values())):
            raise ValueError("snapshot matrices must each be 512 bytes")
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
        if value["schema_version"] == 3:
            pictures = [bytes.fromhex(raw) for raw in value["pictures"]]
            if len(pictures) != 5 or any(len(p) != 378 for p in pictures):
                raise ValueError("snapshot requires five 378-byte RGB pictures")
        settings = []
        for key, opcode in (("light", 7), ("side_light", 8), ("options", 9)):
            raw = bytes(value[key]["raw"])
            if len(raw) != 64 or raw[0] != opcode + 128:
                raise ValueError(f"invalid {key} response data")
            payload = bytes([opcode]) + raw[1 : 8 if opcode != 9 else 7]
            settings.append(codec.packet(payload, 7 if opcode == 9 else 8))
        sleep = value["sleep"]
        times = [sleep[k] for k in ("bluetooth", "dongle", "deep_bluetooth", "deep_dongle")]
        sleep_command = codec.sleep_times(*times)
        if min(times[2:]) < 10:
            raise ValueError("deep sleep must be at least 10 seconds")
        codec.bounded(value["profile"], 2, "profile")
        codec.bounded(value["debounce"], 255, "debounce")
        if type(value["auto_os"]) is not bool:
            raise ValueError("auto_os must be boolean")
        return matrices, fn, macros, settings, sleep_command, pictures
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("snapshot has missing or malformed fields") from error


def restore(keyboard, value, backup_path):
    matrices, fn, macros, settings, sleep_command, pictures = validate(value)

    def operation():
        # Save current configuration before the first write; no-clobber is intentional.
        current = capture(keyboard, extra_macro_slots=macros)
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
            for key, command in zip(("light", "side_light", "options"), settings, strict=True):
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
        current = capture(keyboard, extra_macro_slots=range(256))
        current["limitations"] = ["screen pixels are not included"]
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
