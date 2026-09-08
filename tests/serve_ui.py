"""Browser-test harness: every device operation uses simulated firmware."""

import argparse
import tempfile
from pathlib import Path

from conftest import SimulatedKeyboard

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
    with tempfile.TemporaryDirectory() as directory:
        controller = Controller(
            directory, discovery=lambda: [device], transport_factory=lambda _: SimulatedKeyboard()
        )
        with ControlServer(controller, port=args.port, token="ui-test-token") as server:
            server.serve_forever()


if __name__ == "__main__":
    main()
