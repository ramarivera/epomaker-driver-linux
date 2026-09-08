"""Linux host statistics for the Glyph display; no background service is installed."""

import re
import shutil
import time
from pathlib import Path


class Collector:
    def __init__(
        self,
        *,
        proc=Path("/proc"),
        sys=Path("/sys"),
        disk="/",
        interface=None,
        sleep=time.sleep,
        disk_usage=shutil.disk_usage,
    ):
        if interface is not None and not re.fullmatch(r"[A-Za-z0-9_.:-]+", interface):
            raise ValueError("invalid network interface name")
        self.proc, self.sys, self.disk = Path(proc), Path(sys), disk
        self.interface, self.sleep, self.disk_usage = interface, sleep, disk_usage
        self.previous_cpu = None

    def _cpu(self):
        lines = (self.proc / "stat").read_text().splitlines()
        fields = lines[0].split() if lines else []
        if len(fields) < 9 or fields[0] != "cpu":
            raise ValueError("/proc/stat is missing aggregate CPU counters")
        counters = [int(n) for n in fields[1:9]]  # guest time is already included in user/nice
        if min(counters) < 0:
            raise ValueError("negative CPU counter")
        return sum(counters), counters[3] + counters[4]

    def _network(self, warnings):
        interface = self.interface
        if interface is None:
            candidates = []
            route = self.proc / "net/route"
            if route.exists():
                for row in route.read_text().splitlines()[1:]:
                    fields = row.split()
                    if len(fields) >= 8 and fields[1] == "00000000" and int(fields[3], 16) & 1:
                        candidates.append((int(fields[6]), fields[0]))
            if candidates:
                interface = min(candidates)[1]
        if interface is None:
            warnings.append("no default IPv4 interface; network counters unavailable")
            return None, 0, 0
        root = self.sys / "class/net" / interface / "statistics"
        up = int((root / "tx_bytes").read_text())
        down = int((root / "rx_bytes").read_text())
        if min(up, down) < 0:
            raise ValueError("negative network counter")
        return interface, up, down

    def _temperature(self, warnings):
        temperatures = []
        for directory in (self.sys / "class/hwmon").glob("hwmon*"):
            try:
                name = (directory / "name").read_text().strip()
            except OSError:
                warnings.append("a CPU temperature sensor could not be read")
                continue
            if name not in ("coretemp", "k10temp", "zenpower", "cpu_thermal"):
                continue
            for sensor in directory.glob("temp*_input"):
                try:
                    temperatures.append(int(sensor.read_text()) / 1000)
                except (OSError, ValueError):
                    warnings.append("a CPU temperature sensor could not be read")
        valid = [value for value in temperatures if 0 <= value <= 255]
        if not valid:
            warnings.append("CPU temperature unavailable; display receives zero")
            return None
        return int(max(valid) + 0.5)

    def collect(self):
        warnings = []
        if self.previous_cpu is None:
            self.previous_cpu = self._cpu()
            self.sleep(0.1)
        total, idle = self._cpu()
        delta, idle_delta = total - self.previous_cpu[0], idle - self.previous_cpu[1]
        self.previous_cpu = total, idle
        if delta <= 0 or not 0 <= idle_delta <= delta:
            warnings.append("CPU counters did not advance consistently; usage reported as zero")
            cpu = 0
        else:
            cpu = int(100 * (delta - idle_delta) / delta + 0.5)
        memory = {}
        for line in (self.proc / "meminfo").read_text().splitlines():
            key, _, value = line.partition(":")
            if key in ("MemTotal", "MemAvailable"):
                fields = value.split()
                if len(fields) != 2 or fields[1] != "kB":
                    raise ValueError("unexpected memory counter units")
                memory[key] = int(fields[0]) * 1024
        if (
            set(memory) != {"MemTotal", "MemAvailable"}
            or not 0 <= memory["MemAvailable"] <= memory["MemTotal"]
        ):
            raise ValueError("missing or inconsistent memory counters")
        disk = self.disk_usage(self.disk)
        interface, up, down = self._network(warnings)
        temperature = self._temperature(warnings)
        return {
            "disk_available": disk.free,
            "disk_total": disk.total,
            "memory_used": memory["MemTotal"] - memory["MemAvailable"],
            "memory_total": memory["MemTotal"],
            "cpu_usage": cpu,
            "cpu_temperature": temperature,
            "network_up": up,
            "network_down": down,
            "interface": interface,
            "disk_path": str(self.disk),
            "warnings": warnings,
        }
