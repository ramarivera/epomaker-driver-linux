"""HE60 lighting constraints; installer evidence: docs/he60-lite-research.md."""

from . import codec
from .errors import ProtocolError, UnsupportedDevice


class HELightingMixin:
    def _picture_limit(self, picture):
        self._supported()
        return codec.bounded(picture, 2 if self.expected_id == 3727 else 4, "picture bank")

    def get_light(self, *, side=False):
        if side:
            raise UnsupportedDevice("HE60 Lite has no side lighting")
        return codec.parse_light(self._query(codec.packet([0x87]), expected=0x87))

    def set_light(
        self, mode, *, rgb=0xFFFFFF, brightness=4, speed=0, option=0, rainbow=False, side=False
    ):
        self._supported()
        if side or mode == "off":
            raise UnsupportedDevice("HE60 Lite has no side lighting or explicit off effect")
        if mode not in codec.LIGHT_MODES:
            raise ValueError("unsupported HE60 lighting effect")
        maximum = {
            "wave": 3,
            "snake": 1,
            "kaleidoscope": 1,
            "line-wave": 1,
            "circle-wave": 1,
            "music": 2,
        }.get(mode, 0)
        if mode == "picture":
            self._picture_limit(option)
        else:
            codec.bounded(option, maximum, "effect option")
        codec.bounded(speed, 0 if mode in ("solid", "picture", "music", "screen") else 4, "speed")
        if type(rainbow) is not bool:
            raise ValueError("rainbow must be boolean")
        if mode in ("neon", "picture", "screen") and (rainbow or rgb != 0xFFFFFF):
            raise ValueError("this effect has no RGB or rainbow control")
        command = codec.light(
            mode, rgb=rgb, brightness=brightness, speed=speed, option=option, rainbow=rainbow
        )

        def operation():
            self._write([command])
            actual = self.get_light()
            if actual["raw"][1:8] != list(command[1:8]):
                raise ProtocolError("HE60 lighting readback differs")
            return actual

        return self.transport.transaction(operation)

    def read_picture(self, picture=0):
        self._picture_limit(picture)
        return super().read_picture(picture)

    def write_picture(self, colors, picture=0):
        self._picture_limit(picture)

        def operation():
            return super(HELightingMixin, self).write_picture(colors, picture)

        return self.transport.transaction(operation)
