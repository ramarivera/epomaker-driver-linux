"""Apply a Glyph vendor record using a fresh snapshot and a recovery copy."""

from . import profiles, snapshot, vendor_import
from .errors import ProtocolError, UnsupportedDevice


def apply(keyboard, record, backup_path, *, target="Main", profile=0, expected_plan=None):
    """Allocate from live state, save it, then write macros before their bindings."""

    def operation():
        if keyboard.identify().get("device_id") != 3059:
            raise UnsupportedDevice("vendor configuration import supports Glyph only")
        current = snapshot.capture(keyboard)
        planned = vendor_import.plan(record, current, target, profile)
        if expected_plan is not None and planned != expected_plan:
            raise ValueError("macro allocation changed; preview the configuration again")
        profiles.save(backup_path, current)
        try:
            for slot, payload in planned["macros"].items():
                keyboard.write_macro(int(slot), bytes.fromhex(payload))
            matrix = bytes.fromhex(planned["matrix"])
            if target == "Main":
                keyboard.write_matrix(matrix, profile)
            else:
                keyboard.write_fn_matrix(matrix, os_mode=int(target == "Fn Mac"))
        except Exception as error:
            raise ProtocolError(
                f"vendor import stopped; device may be partially changed; "
                f"previous configuration is saved at {backup_path}: {error}"
            ) from error
        return {
            "imported": True,
            "target": target,
            "profile": profile,
            "assignments": planned["assignments"],
            "previous_configuration": str(backup_path),
        }

    return keyboard.transport.transaction(operation)
