"""Schema 6 recovery snapshots for the older YC3121 family."""

from . import codec, profiles
from .errors import ProtocolError
from .models import model_by_id, validate_sleep_times

MODEL_IDS = (1379, 1723)
LIMITATIONS = [
    "screen pixels, unreferenced macro slots and manual OS options are not included",
    "the snapshot addresses Fn layer 0; OS-specific Fn banks are not established",
]


def macro_slots(matrices):
    return sorted({data[i + 2] for data in matrices for i in range(0, 512, 4) if data[i] == 9})


def _identity_model(value):
    if type(value) is not dict:
        raise ValueError("snapshot identity must be an object")
    model_id = value.get("device_id")
    if type(model_id) is not int or model_id not in MODEL_IDS:
        raise ValueError("schema 6 snapshots require an RT100 or Dynatab75X-UK model")
    return model_id


def _matrix_list(value, name, count):
    if type(value) is not list or len(value) != count:
        raise ValueError(f"snapshot requires {count} {name} matrices")
    result = [bytes.fromhex(raw) for raw in value]
    if any(len(matrix) != 512 for matrix in result):
        raise ValueError(f"{name} matrices must be 512 bytes")
    return result


def _raw_light(value):
    if type(value) is not dict or type(value.get("raw")) is not list:
        raise ValueError("snapshot light must include raw response data")
    raw = bytes(value["raw"])
    if len(raw) != 64 or raw[0] != 0x87:
        raise ValueError("invalid YC3121 main-light response data")
    if raw[1] not in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22):
        raise ValueError("unsupported YC3121 light mode")
    if raw[2] not in range(1, 6) or raw[3] > 4:
        raise ValueError("unsupported YC3121 light speed or brightness")
    option = raw[4] >> 4
    option_max = {4: 3, 7: 1, 11: 1, 12: 1, 13: 2, 15: 1, 22: 2}.get(raw[1], 0)
    if option > option_max:
        raise ValueError("unsupported YC3121 light option")
    if raw[1] == 13 and raw[4] & 15:
        raise ValueError("unsupported YC3121 picture-light flags")
    if raw[1] == 22 and raw[4] & 15 not in (0, 4):
        raise ValueError("unsupported YC3121 music-light flags")
    if raw[1] == 21 and raw[4] & 15:
        raise ValueError("unsupported YC3121 screen-light flags")
    if raw[1] not in (13, 21, 22) and raw[4] & 15 > 8:
        raise ValueError("unsupported YC3121 light color flags")
    # Byte 8 is the command checksum when writing and is not part of the
    # response's persisted lighting fields; normalize it and the padding.
    return raw[:8] + bytes(56)


def validate(value):
    """Decode and validate a schema 6 snapshot without device I/O."""
    try:
        if type(value.get("schema_version")) is not int or value["schema_version"] != 6:
            raise ValueError("restoration requires a schema version 6 snapshot")
        model_id = _identity_model(value["identity"])
        matrices = _matrix_list(value["matrices"], "normal", model_by_id(model_id)["layer"])
        if type(value["fn"]) is not dict or set(value["fn"]) != {"physical"}:
            raise ValueError("snapshot Fn data must contain only physical layer 0")
        fn = bytes.fromhex(value["fn"]["physical"])
        if len(fn) != 512:
            raise ValueError("physical Fn matrix must be 512 bytes")
        macros = {}
        if type(value["macros"]) is not dict:
            raise ValueError("snapshot macros must be an object")
        for key, raw in value["macros"].items():
            slot = codec.bounded(int(key), 255, "macro slot")
            if str(slot) != key:
                raise ValueError("macro slot must be canonical decimal")
            data = bytes.fromhex(raw)
            if len(data) != 256:
                raise ValueError("macro must be 256 bytes")
            macros[slot] = data
        if not set(macro_slots(matrices + [fn])) <= set(macros):
            raise ValueError("snapshot omits a referenced macro")
        picture = bytes.fromhex(value["picture"])
        if len(picture) != 384:
            raise ValueError("snapshot picture must contain 128 RGB triples")
        light = _raw_light(value["light"])
        sleep = value["sleep"]
        names = ("bluetooth", "dongle", "deep_bluetooth", "deep_dongle")
        if type(sleep) is not dict or set(sleep) != set(names):
            raise ValueError("snapshot requires exactly four YC3121 sleep timers")
        times = [sleep[name] for name in names]
        validate_sleep_times(model_id, times)
        debounce = codec.bounded(value["debounce"], 255, "debounce")
        if type(value["auto_os"]) is not bool:
            raise ValueError("auto_os must be boolean")
        profile = codec.bounded(value["profile"], len(matrices) - 1, "profile")
        return (
            model_id,
            matrices,
            fn,
            macros,
            picture,
            light,
            sleep,
            debounce,
            value["auto_os"],
            profile,
        )
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("snapshot has missing or malformed fields") from error


def capture(keyboard, *, extra_macro_slots=()):
    def operation():
        identity = keyboard.identify()
        _identity_model(identity)
        matrices = [keyboard.read_matrix(profile) for profile in range(3)]
        fn = keyboard.read_fn_matrix()
        slots = sorted(set(macro_slots(matrices + [fn])) | set(extra_macro_slots))
        macros = {str(slot): keyboard.read_macro(slot).hex() for slot in slots}
        status = keyboard.status()
        value = {
            "schema_version": 6,
            "identity": identity,
            "matrices": [matrix.hex() for matrix in matrices],
            "fn": {"physical": fn.hex()},
            "macros": macros,
            "picture": keyboard.read_picture(0).hex(),
            "light": {"raw": list(_raw_light({"raw": keyboard.get_light()["raw"]}))},
            "sleep": keyboard.get_sleep(),
            "debounce": status["debounce"],
            "auto_os": keyboard.get_auto_os(),
            "profile": status["profile"],
            "limitations": LIMITATIONS.copy(),
        }
        validate(value)
        return value

    return keyboard.transport.transaction(operation)


def _write_light(keyboard, raw):
    keyboard._supported()
    keyboard.transport.send(codec.packet(bytes([7]) + raw[1:8], 8))
    keyboard.transport.sleep(1.0)
    if bytes(keyboard.get_light()["raw"])[1:8] != raw[1:8]:
        raise ProtocolError("light readback differs")


def restore(keyboard, value, backup_path):
    model_id, matrices, fn, macros, picture, light, sleep, debounce, auto_os, profile = validate(
        value
    )

    def operation():
        identity = keyboard.identify()
        if identity["device_id"] != model_id:
            raise ValueError("snapshot model does not match the connected keyboard")
        current = capture(keyboard, extra_macro_slots=macros)
        validate(current)
        profiles.save(backup_path, current)
        try:
            for slot, data in macros.items():
                keyboard.write_macro(slot, data)
            for index, matrix in enumerate(matrices):
                keyboard.write_matrix(matrix, index)
            keyboard.write_fn_matrix(fn)
            keyboard.write_picture(picture, 0)
            _write_light(keyboard, light)
            keyboard.set_sleep(
                sleep["bluetooth"],
                sleep["dongle"],
                sleep["deep_bluetooth"],
                sleep["deep_dongle"],
            )
            keyboard.set_debounce(debounce)
            keyboard.set_auto_os(auto_os)
            keyboard.set_profile(profile)
        except Exception as error:
            raise ProtocolError(
                f"restore stopped; device may be partially changed; previous configuration is saved at {backup_path}: {error}"
            ) from error
        return {
            "restored": True,
            "previous_configuration": str(backup_path),
            "limitations": LIMITATIONS.copy(),
        }

    return keyboard.transport.transaction(operation)
