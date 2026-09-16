"""Browser-test harness: every device operation uses simulated firmware."""

import argparse
import tempfile
import time
from pathlib import Path

from conftest import SimulatedKeyboard

from epomaker_driver.discovery import DeviceInfo
from epomaker_driver.errors import ProtocolError
from epomaker_driver.server import Controller, ControlServer


class ScreenEraseSimulator(SimulatedKeyboard):
    """Exercise the real erase API/manager without opening any HID device."""

    def __init__(self, kind, delay):
        super().__init__(kind)
        self.vendor_reports = {0: 64} if kind == "usb" else {6: 65}
        self.erase_delay = delay

    def exchange(self, command, **options):
        if command[0] == 0xAC:
            self.sent.append(command)
            return bytes.fromhex("acaaaa5555") + bytes(59)
        return super().exchange(command, **options)

    def prepare_screen_erase_wait(self):
        return 0

    def wait_screen_erase(self, token, *, timeout, cancel, progress):
        started = time.monotonic()
        while time.monotonic() - started < self.erase_delay:
            if cancel.wait(0.05):
                raise ProtocolError("simulated screen erase interrupted; outcome unknown")
            progress(time.monotonic() - started)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8933)
    parser.add_argument("--erase-delay", type=float, default=0.5)
    args = parser.parse_args()
    descriptor = (Path(__file__).parent / "fixtures/glyph-bluetooth-descriptor.bin").read_bytes()
    device = DeviceInfo(
        "/dev/hidraw-test", "Glyph simulator", 5, 0x3151, 0x5004, descriptor, "bluetooth", 6
    )
    usb_device = DeviceInfo(
        "/dev/hidraw-usb-test", "Glyph USB simulator", 3, 0x3151, 0x5002, b"", "usb", 0
    )
    with tempfile.TemporaryDirectory() as directory:
        controller = Controller(
            directory,
            discovery=lambda: [device, usb_device],
            transport_factory=lambda info: ScreenEraseSimulator(
                info.command_transport, args.erase_delay
            ),
        )
        with ControlServer(controller, port=args.port, token="ui-test-token") as server:
            server.serve_forever()


if __name__ == "__main__":
    main()
