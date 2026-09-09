"""Controller-owned background Glyph system-information refresh."""

from __future__ import annotations

import math
import threading


class SystemInfoRefresh:
    def __init__(self, controller, collector_factory):
        self.controller = controller
        self.collector_factory = collector_factory
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._state = {
            "running": False,
            "interval": None,
            "disk": "/",
            "interface": None,
            "samples": 0,
            "last_sample": None,
            "error": None,
        }

    def status(self):
        with self._lock:
            return dict(self._state)

    def start(self, keyboard, interval, disk="/", interface=None):
        if (
            isinstance(interval, bool)
            or not isinstance(interval, (int, float))
            or not math.isfinite(interval)
        ):
            raise ValueError("refresh interval must be a finite number")
        if not 1 <= interval <= 3600:
            raise ValueError("refresh interval must be between 1 and 3600 seconds")
        if type(disk) is not str or not disk:
            raise ValueError("disk must be a nonempty string")
        if interface is not None and (type(interface) is not str or not interface):
            raise ValueError("interface must be a nonempty string or null")
        if self.status()["running"]:
            raise ValueError("system-information refresh is already running")
        self.stop()
        collector = self.collector_factory(disk=disk, interface=interface)
        self._stop = threading.Event()
        with self._lock:
            self._state = {
                "running": True,
                "interval": interval,
                "disk": disk,
                "interface": interface,
                "samples": 0,
                "last_sample": None,
                "error": None,
            }
        self._thread = threading.Thread(
            target=self._run, args=(keyboard, collector, interval), daemon=True
        )
        self._thread.start()
        return self.status()

    def stop(self):
        event = self._stop
        thread = self._thread
        event.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join()
        self._thread = None
        with self._lock:
            self._state["running"] = False
        return self.status()

    def _run(self, keyboard, collector, interval):
        while not self._stop.is_set():
            acquired = False
            try:
                while not self._stop.is_set():
                    acquired = self.controller.lock.acquire(timeout=0.1)
                    if acquired:
                        break
                if self._stop.is_set():
                    return
                sample = collector.collect()
                if self._stop.is_set():
                    return
                keyboard.sync_system_info(sample)
                with self._lock:
                    self._state["samples"] += 1
                    self._state["last_sample"] = sample
            except Exception as error:
                with self._lock:
                    self._state["error"] = str(error)
                    self._state["running"] = False
                self._stop.set()
                return
            finally:
                if acquired:
                    self.controller.lock.release()
            if self._stop.wait(interval):
                return
        with self._lock:
            self._state["running"] = False
