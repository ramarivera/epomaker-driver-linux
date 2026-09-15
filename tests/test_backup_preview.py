import copy

import pytest

from epomaker_driver import snapshot
from epomaker_driver.device import Keyboard
from epomaker_driver.server import Controller


def test_complete_preview_is_offline_and_reports_all_managed_data(firmware, tmp_path):
    value = snapshot.capture(Keyboard(firmware))
    before = list(firmware.sent)
    controller = Controller(tmp_path / "backups")
    assert controller.call("backup_validate", {"value": value}) == {
        "model_id": 3059,
        "profile_count": 3,
        "macro_slot_count": 256,
        "picture_bank_count": 5,
        "limitations": ["screen pixels are not included"],
    }
    value["macros"].pop("255")
    assert (
        "snapshot omits 1 macro slot; omitted slots are left unchanged"
        in snapshot.describe(value)["limitations"]
    )
    assert controller.keyboard is None
    assert firmware.sent == before
    assert not (tmp_path / "backups").exists()


def test_partial_legacy_preview_matches_restore_limitations(firmware, tmp_path):
    keyboard = Keyboard(firmware)
    value = snapshot.capture(keyboard)
    value["schema_version"] = 2
    value.pop("pictures")
    value["debounce"] = 8
    value["macros"] = {
        slot: raw
        for slot, raw in value["macros"].items()
        if int(slot)
        in snapshot.macro_slots(
            [bytes.fromhex(m) for m in value["matrices"]]
            + [bytes.fromhex(m) for m in value["fn"].values()]
        )
    }
    report = snapshot.describe(value)
    assert report["macro_slot_count"] < 256
    assert report["picture_bank_count"] == 0
    assert any("omitted slots are left unchanged" in item for item in report["limitations"])
    assert "legacy Glyph debounce value is not restored" in report["limitations"]
    assert "version 2 snapshot leaves custom RGB pictures unchanged" in report["limitations"]
    result = snapshot.restore(keyboard, value, tmp_path / "recovery.json")
    assert result["limitations"] == report["limitations"]


def test_invalid_preview_uses_full_snapshot_validation(firmware, tmp_path):
    original = snapshot.capture(Keyboard(firmware))
    controller = Controller(tmp_path / "backups")
    for field, replacement in [
        ("matrices", []),
        ("pictures", []),
        ("macros", {"0": "bad"}),
        ("auto_os", 1),
    ]:
        value = copy.deepcopy(original)
        value[field] = replacement
        with pytest.raises(ValueError):
            controller.call("backup_validate", {"value": value})
    assert not (tmp_path / "backups").exists()
