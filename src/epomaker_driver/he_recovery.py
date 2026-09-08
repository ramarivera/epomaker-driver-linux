"""Raw magnetic configuration restoration; schema and limits in docs/he-recovery.md."""

from . import codec, he_snapshot, profiles
from .errors import ProtocolError
from .magnetic import encode_write, key_field


def _profile(keyboard):
    return keyboard._query(codec.packet([0x84]), expected=0x84)[1]


def _expect_profile(keyboard, expected):
    if _profile(keyboard) != expected:
        raise ProtocolError("active profile changed during magnetic restoration")


def _write_profile(keyboard, index, target, current):
    keyboard.set_profile(index)
    for mode, matrix in enumerate(target["matrices"]):
        _expect_profile(keyboard, index)
        if matrix != current["matrices"][mode]:
            keyboard._write(
                list(codec.matrix_chunks(matrix, index, mode, profile_max=keyboard._profile_max()))
            )
        if keyboard.read_matrix(index, mode=mode) != matrix:
            raise ProtocolError("restored submode matrix readback differs")
    # Mode first, then its parameters; field 10's stage-major read layout maps
    # to four-byte simple-write field 8. Axis type uses a separate commit.
    order = [7, 0, 1, 6, 2, 3, 4, 10, 5, 9, 251]
    for slot in range(128):
        mode_changed = target["fields"][7][slot] != current["fields"][7][slot]
        commands = []
        for field in order:
            if field not in target["fields"]:
                continue
            if field == 10:
                wanted = bytes(
                    key_field(target["fields"][10], slot, field=10, stage=s) for s in range(4)
                )
                previous = bytes(
                    key_field(current["fields"][10], slot, field=10, stage=s) for s in range(4)
                )
                wire_field = 8
            else:
                wanted = key_field(target["fields"][field], slot, field=field)
                previous = key_field(current["fields"][field], slot, field=field)
                wire_field = field
            if wanted != previous or mode_changed:
                commands.append((wire_field, wanted))
        if commands:
            _expect_profile(keyboard, index)
            keyboard._write(
                [
                    encode_write(field, slot, raw, commit=n == len(commands) - 1)
                    for n, (field, raw) in enumerate(commands)
                ]
            )
        if 252 in target["fields"]:
            wanted = key_field(target["fields"][252], slot, field=252)
            if wanted != key_field(current["fields"][252], slot, field=252) or mode_changed:
                _expect_profile(keyboard, index)
                keyboard._write([encode_write(252, slot, wanted, commit=True)])
    _expect_profile(keyboard, index)
    for field, raw in target["fields"].items():
        if keyboard._read_field(field, len(raw)) != raw:
            raise ProtocolError(f"magnetic field {field} readback differs in profile {index}")
    for mode, matrix in enumerate(target["matrices"]):
        if keyboard.read_matrix(index, mode=mode) != matrix:
            raise ProtocolError("magnetic writes changed a restored action matrix")
    _expect_profile(keyboard, index)


def _settings(keyboard, target):
    for name, opcode, end in (("light", 7, 8), ("side_light", 8, 8), ("options", 9, 7)):
        raw = target[name]
        if raw is None:
            continue
        keyboard._write([codec.packet(bytes([opcode]) + raw[1:end], end)])
        actual = (
            keyboard.get_options()
            if name == "options"
            else keyboard.get_light(side=name == "side_light")
        )
        if bytes(actual["raw"])[1:end] != raw[1:end]:
            raise ProtocolError(f"{name} readback differs")
    if target["sleep"] is not None:
        raw = target["sleep"]
        keyboard._write([codec.packet(bytes([0x11]) + bytes(7) + raw[8:16])])
        if keyboard._query(codec.packet([0x91]), expected=0x91)[8:16] != raw[8:16]:
            raise ProtocolError("sleep readback differs")
    if target["debounce"] is not None:
        keyboard.set_debounce(target["debounce"])
    keyboard.set_auto_os(target["auto_os"])


def _compare(target, actual):
    for key in (
        "versions",
        "profiles",
        "fn",
        "macros",
        "pictures",
        "auto_os",
        "debounce",
        "profile",
    ):
        if actual[key] != target[key]:
            raise ProtocolError(f"final {key} verification differs")
    for key, start, end in (
        ("light", 1, 8),
        ("side_light", 1, 8),
        ("options", 1, 7),
        ("sleep", 8, 16),
    ):
        wanted, got = target[key], actual[key]
        if wanted is None:
            if got is not None:
                raise ProtocolError(f"final {key} verification differs")
        elif got is None or got[start:end] != wanted[start:end]:
            raise ProtocolError(f"final {key} verification differs")


def restore(keyboard, value, backup_path):
    target = he_snapshot.validate(value)

    def operation():
        identity = keyboard.identify()
        if identity["device_id"] != target["identity"]["device_id"]:
            raise ValueError("snapshot model does not match the connected keyboard")
        current_value = he_snapshot.capture(keyboard)
        current = he_snapshot.validate(current_value)
        if current["versions"] != target["versions"]:
            raise ValueError(
                "snapshot firmware versions do not match; raw magnetic units cannot be migrated implicitly"
            )
        profiles.save(backup_path, current_value)
        try:
            for slot, raw in target["macros"].items():
                if raw != current["macros"][slot]:
                    keyboard.write_macro(slot, raw)
            for index, row in enumerate(target["profiles"]):
                _write_profile(keyboard, index, row, current["profiles"][index])
            for name, raw in target["fn"].items():
                keyboard.write_fn_matrix(raw, os_mode=0 if name == "win" else 1)
            for bank, raw in enumerate(target["pictures"]):
                if raw != current["pictures"][bank]:
                    keyboard.write_picture(raw, bank)
            _settings(keyboard, target)
            keyboard.set_profile(target["profile"])
            actual = he_snapshot.validate(he_snapshot.capture(keyboard))
            _compare(target, actual)
        except BaseException as error:
            cleanup = ""
            try:
                keyboard.set_profile(current["profile"])
            except BaseException as stop_error:
                cleanup = f"; original profile could not be restored: {type(stop_error).__name__}: {stop_error}"
            raise ProtocolError(
                f"restore stopped; device may be partially changed; previous configuration is saved at {backup_path}: "
                f"{type(error).__name__}: {error}{cleanup}"
            ) from error
        return {
            "restored": True,
            "previous_configuration": str(backup_path),
            "limitations": value["limitations"],
        }

    return keyboard.transport.transaction(operation)
