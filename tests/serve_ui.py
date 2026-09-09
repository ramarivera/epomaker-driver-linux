"""Browser-test harness: every device operation uses simulated firmware."""

import argparse
import tempfile
from pathlib import Path

from conftest import SimulatedKeyboard
from he_snapshot_firmware import snapshot_keyboard
from test_yc3121 import Firmware as LegacyFirmware

from epomaker_driver.models import data_file, default_matrix
from epomaker_driver.transport import Transport

from epomaker_driver.discovery import DeviceInfo
from epomaker_driver.server import Controller, ControlServer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8933)
    args = parser.parse_args()
    descriptor = (Path(__file__).parent / "fixtures/glyph-bluetooth-descriptor.bin").read_bytes()
    device = DeviceInfo(
        "/dev/hidraw-test", "Glyph simulator", 5, 0x3151, 0x5004, descriptor, "bluetooth", 6
    )
    devices = [device]
    models = {
        "/dev/he65-mag": (2376, "HE65 Mag simulator", 0x502F),
        "/dev/he65-v2": (3417, "HE65 V2 simulator", 0x5030),
        "/dev/he60-lite": (3727, "HE60 Lite simulator", 0x502C),
        "/dev/rt85": (2895, "RT85 simulator", 0x5002),
        "/dev/rt100-legacy": (1379, "RT100 legacy simulator", 0x4015),
    }
    devices.extend(
        DeviceInfo(path, name, 3, 0x3151, pid, b"", "usb", 0)
        for path, (_, name, pid) in models.items()
    )

    def simulated_transport(info):
        if info.path == device.path:
            return SimulatedKeyboard()
        model = models[info.path][0]
        if model == 1379:
            return Transport(LegacyFirmware(model), "usb", sleep=lambda _: None)
        if model == 2895:
            fw = SimulatedKeyboard()
            fw.model_id = model
            fw.matrices = [bytearray(default_matrix(model)) for _ in range(4)]
            fw.fn = [
                bytearray(default_matrix(model, name))
                for name in ("defaultFnMatrix", "defaultFnMacMatrix")
            ]
            return fw
        keyboard, firmware = snapshot_keyboard(model)
        arrays = data_file("he60-matrices.json")[str(model)]
        firmware.matrices = {key: bytes(arrays["defaultMatrix"]) for key in firmware.matrices}
        firmware.fn = {
            (0, i): bytes(arrays[name])
            for i, name in enumerate(("defaultFnMatrix", "defaultFnMacMatrix"))
        }
        exchange = firmware.exchange

        def display_exchange(command):
            if command[0] == 0xA5:
                firmware.query_log.append(bytes(command))
                return bytes([0xA5, 1]) + bytes(62)
            return exchange(command)

        firmware.exchange = display_exchange
        return keyboard.transport

    with tempfile.TemporaryDirectory() as directory:
        controller = Controller(
            directory, discovery=lambda: devices, transport_factory=simulated_transport
        )
        with ControlServer(controller, port=args.port, token="ui-test-token") as server:
            server.serve_forever()


if __name__ == "__main__":
    main()
