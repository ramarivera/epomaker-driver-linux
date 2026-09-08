"""Profile-aware magnetic firmware for snapshot/recovery integration tests."""

from test_he import Firmware, keyboard

from epomaker_driver import codec
from epomaker_driver.models import RY5088_IDS


class SnapshotFirmware(Firmware):
    def __init__(self, model_id=3692):
        super().__init__(model_id=model_id)
        count = 4 if model_id in RY5088_IDS and model_id != 3518 else 2
        self.profile_fields = {p: dict(self.fields) for p in range(count)}
        for p, fields in self.profile_fields.items():
            fields[0] = (200 + p).to_bytes(2, "little") * 128
            fields[7] = bytes([0] * 128)
            fields[252] = bytes([255 - p] * 128)
        self.fields = self.profile_fields[0]
        self.light = bytearray(codec.light("solid"))
        self.light[0] = 0x87
        self.side_light = bytearray(codec.light("wave", side=True))
        self.side_light[0] = 0x88
        self.macros[255] = bytes([255]) * 256
        self.fail_query = None
        self.drop_raw_setting = None

    def exchange(self, command):
        if self.fail_query == command[0]:
            raise RuntimeError("injected capture failure")
        if command[0] == 0x88:
            self.query_log.append(bytes(command))
            return bytes(self.side_light)
        return super().exchange(command)

    def send(self, command):
        if command[0] == self.drop_raw_setting:
            self.sent.append(bytes(command))
            return
        if command[0] == 0x08:
            self.sent.append(bytes(command))
            self.side_light = bytearray(command)
            self.side_light[0] = 0x88
            return
        super().send(command)
        if command[0] == 4:
            self.fields = self.profile_fields[self.profile]


def snapshot_keyboard(model_id=3692):
    from epomaker_driver.he import HE_PRODUCTS

    product = next(pid for pid, ids in HE_PRODUCTS.items() if model_id in ids)
    fw = SnapshotFirmware(model_id)
    return keyboard(fw, product=product), fw
