"""Serialized app-owned live-light sessions; see docs/releases/glyph-live-light-audit.md."""

import re
import uuid

from . import codec
from .errors import ProtocolError, UnsupportedDevice


class LiveLightSession:
    """All methods run under the owning Controller's lock."""

    def __init__(self):
        self.session = None
        self.keyboard = None
        self.saved = None

    def cancel(self):
        self.session = self.keyboard = self.saved = None

    def start(self, keyboard):
        if self.session is not None:
            raise ValueError(
                "live lighting is already running; stop it in its browser tab, "
                "apply a lighting setting, or disconnect before starting again"
            )
        identity = keyboard.identify()
        if (
            identity["device_id"] != 3059
            or identity["is_boot"]
            or getattr(keyboard.transport, "kind", None) != "usb"
            or identity["light_sync"] is not True
        ):
            raise UnsupportedDevice(
                "Glyph live lighting requires wired USB and firmware light-sync support"
            )
        saved = keyboard.get_light()["raw"]
        # Reapply the exact stored main-light parameters on explicit stop, even
        # for an unknown effect; encoding from UI names would lose raw options.
        self.saved = codec.packet(bytes([7]) + bytes(saved[1:8]), 8)
        self.keyboard = keyboard
        self.session = uuid.uuid4().hex
        try:
            # The vendor switches these autonomous host-follow effects to solid
            # before live frames. Other onboard effect settings are left intact.
            if saved[1] in (21, 22):
                keyboard.set_light("solid")
        except Exception:
            self.cancel()
            raise
        return {"session": self.session}

    def stop(self, session):
        # Late cleanup from an old browser session cannot stop its replacement.
        if session != self.session or self.session is None:
            return {"ok": True}
        keyboard, saved = self.keyboard, self.saved
        self.cancel()
        keyboard._write([saved])
        if bytes(keyboard.get_light()["raw"])[1:8] != saved[1:8]:
            raise ProtocolError("prior lighting restoration readback differs")
        return {"ok": True}

    def frame(self, session, colors):
        if self.session is None or session != self.session:
            raise ValueError("live-light session ended; start again")
        if not isinstance(colors, str) or re.fullmatch(r"[0-9a-fA-F]{756}", colors) is None:
            raise ValueError("live colors must contain exactly 378 RGB bytes as hexadecimal")
        try:
            self.keyboard.send_live_colors(bytes.fromhex(colors))
        except Exception as error:
            try:
                self.stop(session)
            except Exception as restore_error:
                raise ProtocolError(
                    f"live lighting failed: {error}; prior lighting could not be restored: {restore_error}"
                ) from error
            raise
        return {"ok": True}
