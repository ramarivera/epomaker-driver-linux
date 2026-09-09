import time

import pytest

from epomaker_driver import server
from epomaker_driver.discovery import DeviceInfo
from epomaker_driver.errors import DeviceUnavailable
from epomaker_driver.server import Controller


class Collector:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = 0

    def collect(self):
        self.calls += 1
        return {
            "disk_available": 1,
            "disk_total": 2,
            "memory_used": 1,
            "memory_total": 2,
            "cpu_usage": self.calls,
            "cpu_temperature": 20,
            "network_up": 1,
            "network_down": 2,
        }


def make_controller(tmp_path, firmware, descriptor, collector=Collector, model=3059):
    firmware.model_id = model
    info = DeviceInfo("/dev/hidraw-test", "sim", 3, 0x3151, 0x5002, descriptor, "usb", 0)
    return Controller(
        tmp_path / "backups",
        discovery=lambda: [info],
        transport_factory=lambda _: firmware,
        collector_factory=collector,
    )


def wait_for_sample(controller):
    for _ in range(100):
        if controller.call("system_info_refresh", {})["samples"]:
            return
        time.sleep(0.01)
    raise AssertionError("refresh did not collect immediately")


def test_refresh_first_sample_status_and_stop(tmp_path, firmware, descriptor):
    ctl = make_controller(tmp_path, firmware, descriptor)
    info = ctl.discovery()[0]
    ctl.call("connect", {"path": info.path})
    assert ctl.call("system_info_refresh", {})["running"] is False
    started = ctl.call(
        "system_info_refresh_start", {"interval": 1, "disk": "/tmp", "interface": "eth0"}
    )
    assert started["running"] is True and started["disk"] == "/tmp"
    wait_for_sample(ctl)
    assert ctl.call("system_info_refresh", {})["last_sample"]["cpu_usage"] == 1
    stopped = ctl.call("system_info_refresh_stop", {})
    assert stopped["running"] is False
    sent = len(firmware.sent)
    time.sleep(0.05)
    assert len(firmware.sent) == sent


def test_refresh_rejects_duplicate_and_invalid_configuration(tmp_path, firmware, descriptor):
    ctl = make_controller(tmp_path, firmware, descriptor)
    ctl.call("connect", {"path": ctl.discovery()[0].path})
    ctl.call("system_info_refresh_start", {"interval": 1})
    with pytest.raises(ValueError, match="already running"):
        ctl.call("system_info_refresh_start", {"interval": 1})
    ctl.call("system_info_refresh_stop", {})
    for interval in (True, 0, 3601, float("inf"), "1"):
        with pytest.raises(ValueError, match="interval"):
            ctl.call("system_info_refresh_start", {"interval": interval})
    with pytest.raises(ValueError, match="disk"):
        ctl.call("system_info_refresh_start", {"interval": 1, "disk": ""})
    with pytest.raises(ValueError, match="interface"):
        ctl.call("system_info_refresh_start", {"interval": 1, "interface": ""})
    with pytest.raises(ValueError, match="interface"):
        ctl.call("system_info_refresh_start", {"interval": 1, "interface": 3})


def test_refresh_requires_glyph_and_stops_on_disconnect(tmp_path, firmware, descriptor):
    ctl = make_controller(tmp_path, firmware, descriptor)
    ctl.call("connect", {"path": ctl.discovery()[0].path})
    ctl.call("system_info_refresh_start", {"interval": 1})
    ctl.call("disconnect", {})
    assert ctl.call("system_info_refresh", {})["running"] is False
    ctl.call("connect", {"path": ctl.discovery()[0].path})
    ctl.call("system_info_refresh_start", {"interval": 1})
    ctl.call("connect", {"path": ctl.discovery()[0].path})
    assert ctl.call("system_info_refresh", {})["running"] is False
    firmware.model_id = 2895
    ctl.call("disconnect", {})
    with pytest.raises(DeviceUnavailable, match="Glyph"):
        ctl.call("system_info_refresh_start", {"interval": 1})


def test_connected_non_glyph_is_rejected(tmp_path, firmware, descriptor):
    ctl = make_controller(tmp_path, firmware, descriptor)
    ctl.call("connect", {"path": ctl.discovery()[0].path})
    ctl.identity["device_id"] = 2895
    with pytest.raises(DeviceUnavailable, match="Glyph"):
        ctl.call("system_info_refresh_start", {"interval": 1})


def test_refresh_captures_failure_and_stops(tmp_path, firmware, descriptor):
    class Broken:
        def __init__(self, **kwargs):
            pass

        def collect(self):
            raise RuntimeError("collector failed")

    ctl = make_controller(tmp_path, firmware, descriptor, collector=Broken)
    ctl.call("connect", {"path": ctl.discovery()[0].path})
    ctl.call("system_info_refresh_start", {"interval": 1})
    for _ in range(100):
        status = ctl.call("system_info_refresh", {})
        if status["error"]:
            break
        time.sleep(0.01)
    assert status["running"] is False
    assert status["error"] == "collector failed"


def test_refresh_reuses_collector_for_later_samples(tmp_path, firmware, descriptor):
    collectors = []

    def factory(**kwargs):
        collector = Collector(**kwargs)
        collectors.append(collector)
        return collector

    ctl = make_controller(tmp_path, firmware, descriptor, collector=factory)
    ctl.call("connect", {"path": ctl.discovery()[0].path})
    ctl.call("system_info_refresh_start", {"interval": 1})
    wait_for_sample(ctl)
    time.sleep(1.1)
    assert ctl.call("system_info_refresh", {})["samples"] >= 2
    assert len(collectors) == 1
    ctl.call("system_info_refresh_stop", {})


def test_stop_while_worker_waits_for_controller_lock_has_no_late_write(
    tmp_path, firmware, descriptor
):
    ctl = make_controller(tmp_path, firmware, descriptor)
    ctl.call("connect", {"path": ctl.discovery()[0].path})
    ctl.lock.acquire()
    try:
        ctl.call("system_info_refresh_start", {"interval": 1})
        ctl.system_info_refresh.stop()
        sent = len(firmware.sent)
    finally:
        ctl.lock.release()
    time.sleep(0.05)
    assert len(firmware.sent) == sent
    assert ctl.call("system_info_refresh", {})["running"] is False


def test_refresh_stops_before_reset_restore_and_server_close(
    tmp_path, firmware, descriptor, monkeypatch
):
    ctl = make_controller(tmp_path, firmware, descriptor)
    ctl.call("connect", {"path": ctl.discovery()[0].path})
    ctl.call("system_info_refresh_start", {"interval": 1})
    observed = []

    def fake_reset(keyboard, backup):
        observed.append(ctl.call("system_info_refresh", {})["running"])
        return {"backup": str(backup)}

    monkeypatch.setattr(server.snapshot, "factory_reset", fake_reset)
    ctl.call("write", {"kind": "factory_reset"})
    assert observed == [False]

    ctl = make_controller(tmp_path / "restore", firmware, descriptor)
    ctl.call("connect", {"path": ctl.discovery()[0].path})
    ctl.call("system_info_refresh_start", {"interval": 1})
    monkeypatch.setattr(
        server.snapshot,
        "restore",
        lambda keyboard, value, backup: (
            observed.append(ctl.call("system_info_refresh", {})["running"]) or {}
        ),
    )
    ctl.call("write", {"kind": "restore", "value": {}})
    assert observed[-1] is False

    ctl = make_controller(tmp_path / "close", firmware, descriptor)
    ctl.call("connect", {"path": ctl.discovery()[0].path})
    ctl.call("system_info_refresh_start", {"interval": 1})
    with server.ControlServer(ctl, web_root=tmp_path) as instance:
        instance.server_close()
    assert ctl.call("system_info_refresh", {})["running"] is False


def test_refresh_stops_on_transport_failure(tmp_path, firmware, descriptor):
    ctl = make_controller(tmp_path, firmware, descriptor)
    ctl.call("connect", {"path": ctl.discovery()[0].path})
    firmware.send = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("transport failed"))
    ctl.call("system_info_refresh_start", {"interval": 1})
    for _ in range(100):
        status = ctl.call("system_info_refresh", {})
        if status["error"]:
            break
        time.sleep(0.01)
    assert status["running"] is False
    assert status["error"] == "transport failed"
