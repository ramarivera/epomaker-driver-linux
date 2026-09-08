"""HE60 lighting constraints; installer evidence: docs/he60-lite-research.md."""

from . import codec
from .errors import ProtocolError, UnsupportedDevice
from .models import RY5088_SIDE_IDS


class HELightingMixin:
    def _picture_limit(self, picture):
        self._supported()
        return codec.bounded(picture, 2 if self.expected_id == 3727 else 4, "picture bank")

    def get_light(self, *, side=False):
        self._supported()
        if side:
            if self.expected_id not in RY5088_SIDE_IDS:
                raise UnsupportedDevice("this HE model has no side-light layout")
            return codec.parse_light(
                self._query(codec.packet([0x88]), expected=0x88), side=True, dazzle=8
            )
        return codec.parse_light(self._query(codec.packet([0x87]), expected=0x87))

    def set_light(
        self, mode, *, rgb=0xFFFFFF, brightness=4, speed=0, option=0, rainbow=False, side=False
    ):
        self._supported()
        if side:
            if self.expected_id not in RY5088_SIDE_IDS:
                raise UnsupportedDevice("this HE model has no side-light layout")
            if mode not in codec.SIDE_MODES:
                raise ValueError("unsupported HE side-lighting effect")
            codec.bounded(option, 0, "side effect option")
            codec.bounded(speed, 0 if mode in ("off", "solid") else 3, "side speed")
            if mode == "off" and brightness != 4:
                raise ValueError("side off has no brightness control")
            if type(rainbow) is not bool:
                raise ValueError("rainbow must be boolean")
            if mode in ("off", "neon") and (rainbow or rgb != 0xFFFFFF):
                raise ValueError("this side effect has no RGB or rainbow control")
            command = codec.light(
                mode,
                rgb=rgb,
                brightness=brightness,
                speed=speed,
                option=option,
                rainbow=rainbow,
                side=True,
                side_speed_max=3,
                normal=7,
                dazzle=8,
            )

            def operation():
                self._write([command])
                actual = self.get_light(side=True)
                if actual["raw"][1:8] != list(command[1:8]):
                    raise ProtocolError("HE side-lighting readback differs")
                return actual

            return self.transport.transaction(operation)
        if mode == "off":
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
