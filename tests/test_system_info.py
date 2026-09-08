from types import SimpleNamespace

import pytest

from epomaker_driver import codec
from epomaker_driver.device import Keyboard
from epomaker_driver.system_info import Collector


@pytest.fixture
def collector(tmp_path):
    proc, sys = tmp_path / "proc", tmp_path / "sys"
    proc.mkdir()
    (proc / "net").mkdir()
    (proc / "stat").write_text("cpu 10 0 10 80 0 0 0 0 999 999\n")
    (proc / "meminfo").write_text(
        "MemTotal: 8388608 kB\nMemAvailable: 2097152 kB\nIgnored: 123 kB\n"
    )
    (proc / "net/route").write_text(
        "Iface Destination Gateway Flags RefCnt Use Metric Mask\n"
        "eth0 00000000 00000000 0001 0 0 10 00000000\n"
        "eth1 00000000 00000000 0001 0 0 20 00000000\n"
        "eth2 0100007F 00000000 0001 0 0 1 00000000\n"
    )
    stats = sys / "class/net/eth0/statistics"
    stats.mkdir(parents=True)
    (stats / "tx_bytes").write_text(str(3 * 1024**3))
    (stats / "rx_bytes").write_text(str(4 * 1024**3))
    sensor = sys / "class/hwmon/hwmon0"
    sensor.mkdir(parents=True)
    (sensor / "name").write_text("coretemp\n")
    (sensor / "temp1_input").write_text("55500\n")
    (sensor / "temp2_input").write_text("54000\n")
    other = sensor.parent / "hwmon1"
    other.mkdir()
    (other / "name").write_text("amdgpu\n")
    (other / "temp1_input").write_text("90000\n")

    def advance(_):
        (proc / "stat").write_text("cpu 30 0 30 140 0 0 0 0 9999 9999\n")

    return Collector(
        proc=proc,
        sys=sys,
        sleep=advance,
        disk_usage=lambda _: SimpleNamespace(free=100 * 1024**3, total=200 * 1024**3),
    )


def test_collector_units_and_protocol(collector, firmware):
    value = collector.collect()
    assert value["cpu_usage"] == 40
    assert value["cpu_temperature"] == 56
    assert value["interface"] == "eth0"
    assert value["warnings"] == []
    assert value["memory_used"] == 6 * 1024**3
    packet = codec.system_info(value)
    assert packet[:8] == bytes.fromhex("22000000000000dd")
    assert packet[8:22] == bytes.fromhex("6400c80006000800283803000400")
    Keyboard(firmware).sync_system_info(value)
    assert firmware.sent == [packet]
    assert "CPU counters" in collector.collect()["warnings"][0]


def test_missing_network_and_temperature(collector):
    (collector.proc / "net/route").unlink()
    (collector.sys / "class/hwmon/hwmon0/temp1_input").write_text("bad")
    (collector.sys / "class/hwmon/hwmon0/temp2_input").unlink()
    value = collector.collect()
    assert value["cpu_temperature"] is None and value["interface"] is None
    assert len(value["warnings"]) == 3
    assert codec.system_info(value)[17] == 0


def test_sensor_disappears(collector):
    (collector.sys / "class/hwmon/hwmon0/name").unlink()
    value = collector.collect()
    assert value["cpu_temperature"] is None
    assert any("could not be read" in item for item in value["warnings"])


def test_explicit_interface_and_bad_counters(collector):
    collector.interface = "eth0"
    assert collector.collect()["network_up"] == 3 * 1024**3
    (collector.sys / "class/net/eth0/statistics/tx_bytes").write_text("-1")
    with pytest.raises(ValueError, match="negative network"):
        collector.collect()
    with pytest.raises(ValueError, match="interface name"):
        Collector(interface="../x")


@pytest.mark.parametrize("raw", ["", "bogus 1 2 3 4 5 6 7 8", "cpu 1 2 3", "cpu -1 0 0 1 0 0 0 0"])
def test_bad_cpu_input(collector, raw):
    (collector.proc / "stat").write_text(raw)
    with pytest.raises(ValueError):
        collector.collect()


@pytest.mark.parametrize(
    "raw", ["MemTotal: 1 bytes\n", "MemTotal: 1 kB\n", "MemTotal: 1 kB\nMemAvailable: 2 kB\n"]
)
def test_bad_memory(collector, raw):
    (collector.proc / "meminfo").write_text(raw)
    with pytest.raises(ValueError):
        collector.collect()


def test_protocol_rounding_and_overflow(collector):
    value = collector.collect()
    value["disk_available"] = 1024**3 // 2
    assert codec.system_info(value)[8:10] == bytes([1, 0])
    for field, invalid in (
        ("disk_available", -1),
        ("network_up", 65536 * 1024**3),
        ("cpu_usage", 101),
    ):
        with pytest.raises(ValueError):
            codec.system_info({**value, field: invalid})
