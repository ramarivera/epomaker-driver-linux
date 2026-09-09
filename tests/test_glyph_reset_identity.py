import json

import pytest

from epomaker_driver import snapshot
from epomaker_driver.device import Keyboard
from epomaker_driver.errors import ProtocolError


@pytest.mark.parametrize(
    "field,value", [("device_id", 3223), ("usb_version", 1), ("is_boot", True)]
)
def test_reset_rejects_identity_drift_after_backup(firmware, tmp_path, monkeypatch, field, value):
    keyboard = Keyboard(firmware)
    destination = tmp_path / "before.json"
    identify = keyboard.identify

    def changed():
        result = identify()
        if destination.exists():
            result[field] = value
        return result

    monkeypatch.setattr(keyboard, "identify", changed)
    with pytest.raises(ProtocolError, match="reset was not sent.*identity changed"):
        snapshot.factory_reset(keyboard, destination)
    assert firmware.sent == []
    assert len(json.loads(destination.read_text())["macros"]) == 256
    assert keyboard.identity is None and keyboard.model is None


def test_reset_identity_query_failure_retains_backup_without_reset(firmware, tmp_path, monkeypatch):
    keyboard = Keyboard(firmware)
    destination = tmp_path / "before.json"
    identify = keyboard.identify

    def disconnected():
        if destination.exists():
            raise OSError("disconnected during backup")
        return identify()

    monkeypatch.setattr(keyboard, "identify", disconnected)
    with pytest.raises(ProtocolError, match="reset was not sent.*disconnected during backup"):
        snapshot.factory_reset(keyboard, destination)
    assert destination.exists()
    assert not firmware.sent
    assert keyboard.identity is None and keyboard.model is None
