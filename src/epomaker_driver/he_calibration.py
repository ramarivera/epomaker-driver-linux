"""Modern magnetic travel calibration; installer protocol evidence only."""

from __future__ import annotations

import math

from . import codec
from .errors import ProtocolError, UnsupportedDevice


def validate_duration(value):
    if isinstance(value, bool):
        raise ValueError("calibration seconds must be a finite number")
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            raise ValueError("calibration seconds must be a finite number") from None
    if not isinstance(value, (int, float)):
        raise ValueError("calibration seconds must be a finite number")
    if not 1 <= value <= 300 or not math.isfinite(value):
        raise ValueError("calibration seconds must be between 1 and 300")
    return float(value)


class HECalibrationMixin:
    def _calibration_supported(self):
        if self.transport.kind != "usb":
            raise UnsupportedDevice("magnetic calibration requires USB transport")
        self._supported()

    def read_calibration(self):
        def operation():
            self._calibration_supported()
            pages = []
            for page in range(4):
                command = codec.packet([0xE5, 254, 1, page])
                self._check_commands([command])
                # Raw pages have no echoed opcode/header. Vendor uses 1 ms
                # send/read delays here; see docs/calibration.md.
                response = self.transport.exchange(command, send_delay=0.001, read_delay=0.001)
                if len(response) != 64:
                    raise ProtocolError("calibration response must contain 64 bytes")
                pages.append(response)
            raw = b"".join(pages)
            values = [int.from_bytes(raw[i : i + 2], "little") for i in range(0, 256, 2)]
            return {"raw": raw.hex(), "values": values}

        return self.transport.transaction(operation)

    def calibrate(self, seconds=30, on_progress=None):
        duration = validate_duration(seconds)
        if on_progress is not None and not callable(on_progress):
            raise ValueError("on_progress must be callable")

        def operation():
            self._calibration_supported()
            transport = self.transport

            def progress(event):
                if on_progress is not None:
                    on_progress(event)

            def command(opcode, value):
                self._write([codec.packet([opcode, value])])

            started = False
            samples = 0
            last = None
            try:
                progress({"phase": "release"})
                # A failed send can still have reached the device.
                started = True
                command(0x1C, 1)
                transport.sleep(2.0)
                command(0x1C, 0)
                command(0x1E, 1)
                progress({"phase": "press"})
                deadline = transport.clock() + duration
                while transport.clock() < deadline:
                    last = self.read_calibration()
                    samples += 1
                    progress({"phase": "sample", "sample": last})
                    transport.sleep(min(0.1, max(0, deadline - transport.clock())))
                command(0x1E, 0)
            except BaseException as original:
                if started:
                    failures = []
                    # Independently disable both phases after an uncertain
                    # write, failed read, callback exception or cancellation.
                    for opcode in (0x1C, 0x1E):
                        try:
                            command(opcode, 0)
                        except BaseException as error:
                            failures.append(f"{opcode:02x}: {type(error).__name__}: {error}")
                    if failures:
                        raise ProtocolError(
                            f"calibration cleanup failed ({'; '.join(failures)}); "
                            f"original {type(original).__name__}: {original}"
                        ) from original
                raise
            return {"completed": True, "samples": samples, "last": last, "duration": duration}

        return self.transport.transaction(operation)
