"""Read-only sysfs discovery and HID descriptor inspection.

Only descriptors/device metadata are read here, never input reports. See
https://docs.kernel.org/hid/hidintro.html and docs/provenance.md.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from .errors import ProtocolError


@dataclass(frozen=True)
class Collection:
    usage_page: int
    usage: int


@dataclass
class Report:
    report_id: int
    input_bits: int = 0
    output_bits: int = 0
    feature_bits: int = 0
    collections: set[Collection] = field(default_factory=set)

    def payload_bytes(self, kind: str) -> int:
        if kind not in ("input", "output", "feature"):
            raise ValueError("unknown report kind")
        return (getattr(self, kind + "_bits") + 7) // 8


def parse_descriptor(data: bytes) -> dict[int, Report]:
    """Parse HID short items, global push/pop and application collection membership."""
    reports: dict[int, Report] = {}
    state = {"page": 0, "size": 0, "count": 0, "id": 0}
    stack: list[dict[str, int]] = []
    collections: list[Collection] = []
    usage = 0
    index = 0
    while index < len(data):
        prefix = data[index]
        index += 1
        if prefix == 0xFE:
            if index + 2 > len(data):
                raise ProtocolError("truncated HID long-item header")
            length = data[index]
            index += 2
            if index + length > len(data):
                raise ProtocolError("truncated HID long item")
            index += length
            continue
        length = (0, 1, 2, 4)[prefix & 3]
        if index + length > len(data):
            raise ProtocolError("truncated HID short item")
        value = int.from_bytes(data[index : index + length], "little")
        index += length
        kind, tag = (prefix >> 2) & 3, prefix >> 4
        if kind == 1:
            if tag in (0, 7, 8, 9):
                if tag == 8 and not 1 <= value <= 255:
                    raise ProtocolError("invalid HID report ID")
                state[{0: "page", 7: "size", 8: "id", 9: "count"}[tag]] = value
            elif tag == 10:
                stack.append(state.copy())
            elif tag == 11:
                if not stack:
                    raise ProtocolError("HID global stack underflow")
                state = stack.pop()
        elif kind == 2 and tag == 0:
            usage = value
        elif kind == 0:
            if tag == 10:
                page = usage >> 16 if usage > 0xFFFF else state["page"]
                collections.append(Collection(page, usage & 0xFFFF))
            elif tag == 12:
                if not collections:
                    raise ProtocolError("HID collection stack underflow")
                collections.pop()
            elif tag in (8, 9, 11):
                bits = state["size"] * state["count"]
                if bits > 65536:
                    raise ProtocolError("unreasonable HID report size")
                report = reports.setdefault(state["id"], Report(state["id"]))
                name = {8: "input_bits", 9: "output_bits", 11: "feature_bits"}[tag]
                total = getattr(report, name) + bits
                if total > 65536:
                    raise ProtocolError("unreasonable aggregate HID report size")
                setattr(report, name, total)
                report.collections.update(collections)
            usage = 0
    if collections or stack:
        raise ProtocolError("unbalanced HID descriptor stacks")
    return reports


@dataclass(frozen=True)
class DeviceInfo:
    path: str
    name: str
    bus: int
    vendor_id: int
    product_id: int
    descriptor: bytes
    command_transport: str | None
    report_id: int | None

    def public_dict(self) -> dict:
        value = asdict(self)
        value.pop("descriptor")
        value["vendor_id"] = f"{self.vendor_id:04x}"
        value["product_id"] = f"{self.product_id:04x}"
        return value


def classify(bus: int, vid: int, pid: int, reports: dict[int, Report]):
    # Command collections from installer filters; require matching report sizes.
    # YC3121 USB 0x4015: docs/yc3121.md.
    # RY6602 USB product ID and unverified hardware status: docs/ry6602.md.
    if vid != 0x3151:
        return None, None
    if bus == 5 and pid == 0x5004:
        r = reports.get(6)
        if r and Collection(0xFF55, 0x0202) in r.collections:
            if r.payload_bytes("input") == r.payload_bytes("output") == 65:
                return "bluetooth", 6
    # HE60 Lite filters: docs/he60-lite-research.md; CH585 mice: docs/ch585-protocol.md.
    if bus == 3 and pid in (
        0x4015,
        0x5002,
        0x5029,
        0x502C,
        0x502D,
        0x502E,
        0x502F,
        0x5030,
        0x503A,
        0x5043,
        0x5054,
        0x5056,
    ):
        r = reports.get(0)
        if r and Collection(0xFFFF, 2) in r.collections and r.payload_bytes("feature") == 64:
            return "usb", 0
    return None, None


def discover(root: Path = Path("/sys/class/hidraw")) -> list[DeviceInfo]:
    devices = []
    for entry in sorted(root.glob("hidraw*")):
        try:
            metadata = dict(
                line.split("=", 1)
                for line in (entry / "device/uevent").read_text().splitlines()
                if "=" in line
            )
            bus, vid, pid = (int(part, 16) for part in metadata["HID_ID"].split(":"))
            descriptor = (entry / "device/report_descriptor").read_bytes()
            reports = parse_descriptor(descriptor)
        except FileNotFoundError:
            continue  # Device disconnected during enumeration.
        except (ValueError, KeyError, ProtocolError) as error:
            raise ProtocolError(f"{entry.name}: invalid HID metadata: {error}") from error
        transport, report_id = classify(bus, vid, pid, reports)
        devices.append(
            DeviceInfo(
                "/dev/" + entry.name,
                metadata.get("HID_NAME", ""),
                bus,
                vid,
                pid,
                descriptor,
                transport,
                report_id,
            )
        )
    return devices
