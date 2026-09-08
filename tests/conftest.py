from pathlib import Path

import pytest

from epomaker_driver import codec
from epomaker_driver.models import glyph_matrix


@pytest.fixture
def descriptor():
    return (Path(__file__).parent / "fixtures/glyph-bluetooth-descriptor.bin").read_bytes()


class SimulatedKeyboard:
    """Firmware-side state machine for integration tests, never real hardware."""

    def __init__(self):
        self.sent = []
        self.matrices = [bytearray(glyph_matrix()) for _ in range(3)]
        self.fn = [
            bytearray(glyph_matrix("defaultFnMatrix")),
            bytearray(glyph_matrix("defaultFnMacMatrix")),
        ]
        self.macros = {}
        self.profile = 0
        self.debounce = 5
        self.light = bytearray(codec.light("solid"))
        self.side_light = bytearray(codec.light("solid", side=True))
        self.sleep_data = bytearray(codec.sleep_times(120, 240, 1800, 3600))
        self.model_id = 3059
        self.battery = 80
        self.online = True
        self.closed = False
        self.sleep = lambda _: None
        self.accept_screen = True

    def transaction(self, fn):
        return fn()

    def exchange(self, command, **options):
        op = command[0]
        if op == 0x8F:
            result = bytearray(64)
            result[0] = op
            result[1:5] = self.model_id.to_bytes(4, "little")
            return bytes(result)
        if op in (0x84, 0x83, 0x86):
            result = bytearray(64)
            result[0] = op
            if op == 0x83:
                result[2] = 3
            else:
                result[1] = self.profile if op == 0x84 else self.debounce
            return bytes(result)
        if op in (0x87, 0x88, 0x91):
            result = bytearray({0x87: self.light, 0x88: self.side_light, 0x91: self.sleep_data}[op])
            result[0] = op
            return bytes(result)
        if op == 0x8A:
            return bytes(self.matrices[command[1]][command[3] * 64 : (command[3] + 1) * 64])
        if op == 0x90:
            return bytes(self.fn[command[1]][command[4] * 64 : (command[4] + 1) * 64])
        if op == 0x8B:
            data = self.macros.get(command[1], bytearray(256))
            return bytes(data[command[2] * 64 : (command[2] + 1) * 64])
        if op == 0xA5:
            return bytes([op, int(self.accept_screen)]) + bytes(62)
        raise AssertionError(f"unimplemented simulated query {op:x}")

    def send(self, command, **options):
        self.sent.append(command)
        op = command[0]
        if op == 0x0A:
            matrix = self.matrices[command[1]]
            if command[2] == 255:
                start, count = command[3] * 56, command[4]
                matrix[start : start + count] = command[8 : 8 + count]
            else:
                start = command[2] * 4
                matrix[start : start + 4] = command[8:12]
        elif op == 0x10:
            start = command[3] * 4
            self.fn[command[1]][start : start + 4] = command[8:12]
        elif op == 0x0B:
            matrix = self.macros.setdefault(command[1], bytearray(256))
            start = command[2] * 56
            count = min(56, 256 - start)
            matrix[start : start + count] = command[8 : 8 + count]
        elif op == 4:
            self.profile = command[1]
        elif op == 6:
            self.debounce = command[1]
        elif op == 7:
            self.light = bytearray(command)
        elif op == 8:
            self.side_light = bytearray(command)
        elif op == 0x11:
            self.sleep_data = bytearray(command)

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


@pytest.fixture
def firmware():
    return SimulatedKeyboard()
