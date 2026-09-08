"""HE65 V2 knob slots and vendor UI restrictions; docs/he65-v2.md."""


def knob_slots(model_id):
    # Exact positions in the model's default matrix, matching advertised knobKeyCodes.
    return {"volume-up": 90, "volume-down": 91, "mute": 92} if model_id == 3417 else {}


def validate_knob_binding(model_id, slot, action, *, fn=False):
    if slot not in knob_slots(model_id).values():
        return
    if fn:
        raise ValueError("knob inputs have no editable Fn binding")
    if isinstance(action, (bytes, bytearray, memoryview)) and bytes(action[:2]) == b"\x09\x02":
        raise ValueError("knob inputs do not support held macro playback")


def validate_magnetic_slot(model_id, slot):
    if slot in knob_slots(model_id).values():
        raise ValueError("knob inputs are not magnetic keys")
