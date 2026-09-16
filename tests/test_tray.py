# ruff: noqa: F821
"""Real D-Bus requests on private daemons; never use the desktop session bus."""

import asyncio
import selectors
import subprocess
import threading
from contextlib import asynccontextmanager

import pytest
from dbus_next import PropertyAccess, RequestNameReply, Variant
from dbus_next.aio import MessageBus
from dbus_next.errors import DBusError
from dbus_next.service import ServiceInterface, dbus_property, method

from epomaker_driver import tray as module
from epomaker_driver.tray import Tray, TrayError


@pytest.fixture(autouse=True)
def isolated_session_bus(monkeypatch):
    daemon = subprocess.Popen(
        ["dbus-daemon", "--session", "--nofork", "--print-address=1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(daemon.stdout, selectors.EVENT_READ)
            assert selector.select(3), "test bus did not publish its address"
        address = daemon.stdout.readline().strip()
        assert address
        monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", address)
        monkeypatch.setattr(module, "POLL_INTERVAL", 0.02)
        yield
    finally:
        daemon.terminate()
        daemon.wait(timeout=3)
        daemon.stdout.close()
        daemon.stderr.close()


class FakeWatcher(ServiceInterface):
    def __init__(self, host=True, reject=False):
        super().__init__("org.kde.StatusNotifierWatcher")
        self.host, self.reject = host, reject
        self.registered = threading.Event()
        self.service = ""

    @dbus_property(access=PropertyAccess.READ)
    def IsStatusNotifierHostRegistered(self) -> "b":
        return self.host

    @method()
    def RegisterStatusNotifierItem(self, service: "s"):
        if self.reject:
            raise DBusError("org.kde.Error.Rejected", "test rejection")
        self.service = service
        self.registered.set()


def disconnect(bus):
    # Pinned dbus-next leaves descriptors open after disconnect, including for
    # test clients. Match the adapter's cleanup without touching other buses.
    bus.disconnect()
    bus._finalize()
    bus._stream.close()
    bus._sock.close()


async def watcher_bus(host=True, reject=False):
    bus = await MessageBus().connect()
    watcher = FakeWatcher(host, reject)
    bus.export("/StatusNotifierWatcher", watcher)
    assert await bus.request_name("org.kde.StatusNotifierWatcher") == RequestNameReply.PRIMARY_OWNER
    return bus, watcher


@asynccontextmanager
async def session():
    bus, watcher = await watcher_bus()
    opened, quit_requested = threading.Event(), threading.Event()
    tray = Tray(opened.set, quit_requested.set)
    client = None
    try:
        await asyncio.to_thread(tray.__enter__)
        client = await MessageBus().connect()
        yield tray, client, watcher, bus, opened, quit_requested
    finally:
        await asyncio.to_thread(tray.close)
        if client:
            disconnect(client)
        disconnect(bus)


async def interface(client, service, path, name):
    description = await client.introspect(service, path)
    return client.get_proxy_object(service, path, description).get_interface(name)


def test_real_menu_protocol_and_invalid_requests_never_quit():
    async def check():
        async with session() as (tray, client, watcher, _bus, opened, quit_requested):
            menu = await interface(client, watcher.service, "/Menu", "com.canonical.dbusmenu")
            properties = await interface(
                client, watcher.service, "/Menu", "org.freedesktop.DBus.Properties"
            )
            values = await properties.call_get_all("com.canonical.dbusmenu")
            assert {key: value.value for key, value in values.items()} == {
                "Version": 3,
                "TextDirection": "ltr",
                "Status": "normal",
                "IconThemePath": [],
            }
            revision, layout = await menu.call_get_layout(0, -1, [])
            assert revision == 1 and layout[1]["children-display"].value == "submenu"
            assert [child.value[1]["label"].value for child in layout[2]] == [
                "Open controls",
                "Quit driver",
            ]
            assert (await menu.call_get_layout(0, 0, []))[1][2] == []
            assert set((await menu.call_get_layout(1, 1, ["label"]))[1][1]) == {"label"}
            grouped = await menu.call_get_group_properties([], ["label"])
            assert [item[0] for item in grouped] == [0, 1, 2]
            assert grouped[0][1] == {} and set(grouped[1][1]) == {"label"}
            assert await menu.call_get_group_properties([99], []) == []
            assert (await menu.call_get_property(1, "label")).value == "Open controls"
            for parent, depth in [(99, -1), (0, -2)]:
                with pytest.raises(DBusError):
                    await menu.call_get_layout(parent, depth, [])
            for item_id, name in [(99, "label"), (1, "invalid")]:
                with pytest.raises(DBusError):
                    await menu.call_get_property(item_id, name)
            with pytest.raises(DBusError):
                await menu.call_event(99, "clicked", Variant("s", ""), 0)
            await menu.call_event(0, "clicked", Variant("s", ""), 0)
            await menu.call_event(1, "hovered", Variant("s", ""), 0)
            assert not opened.is_set() and not quit_requested.is_set()
            assert await menu.call_event_group(
                [[99, "clicked", Variant("s", ""), 0], [1, "hovered", Variant("s", ""), 0]]
            ) == [99]
            assert not quit_requested.is_set()
            assert await menu.call_about_to_show(0) is False
            with pytest.raises(DBusError):
                await menu.call_about_to_show(99)
            assert await menu.call_about_to_show_group([0, 1, 99]) == [[], [99]]
            await menu.call_event(1, "clicked", Variant("s", ""), 0)
            assert await asyncio.to_thread(opened.wait, 1)
            await menu.call_event_group([[2, "clicked", Variant("s", ""), 0]])
            assert await asyncio.to_thread(quit_requested.wait, 1)
            with pytest.raises(TrayError, match="reused"):
                tray.__enter__()
        assert not tray._thread.is_alive() and tray._bus._sock.fileno() == -1
        tray.close()

    asyncio.run(check())


def test_item_properties_and_activation_do_not_expose_control_url():
    async def check():
        async with session() as (_tray, client, watcher, _bus, opened, _quit):
            item = await interface(
                client, watcher.service, "/StatusNotifierItem", "org.kde.StatusNotifierItem"
            )
            props = await interface(
                client, watcher.service, "/StatusNotifierItem", "org.freedesktop.DBus.Properties"
            )
            values = await props.call_get_all("org.kde.StatusNotifierItem")
            assert values["IconName"].value == "input-keyboard"
            assert values["Category"].value == "Hardware"
            assert values["Menu"].value == "/Menu" and values["WindowId"].value == 0
            assert values["ItemIsMenu"].value is False and values["Status"].value == "Active"
            assert values["IconPixmap"].value == []
            assert "token" not in repr(values).lower() and "http" not in repr(values).lower()
            await item.call_activate(0, 0)
            assert await asyncio.to_thread(opened.wait, 1)
            opened.clear()
            await item.call_secondary_activate(0, 0)
            assert await asyncio.to_thread(opened.wait, 1)
            await item.call_context_menu(0, 0)
            await item.call_scroll(1, "vertical")

    asyncio.run(check())


@pytest.mark.parametrize("host,reject", [(False, False), (True, True)])
def test_unusable_host_is_actionable_and_cleans_up(host, reject):
    async def check():
        bus, _watcher = await watcher_bus(host, reject)
        tray = Tray(lambda: None, lambda: None)
        try:
            with pytest.raises(TrayError, match="tray host"):
                await asyncio.to_thread(tray.__enter__)
            assert not tray._thread.is_alive() and tray._bus._sock.fileno() == -1
        finally:
            disconnect(bus)

    asyncio.run(check())


def test_missing_watcher_is_actionable():
    with pytest.raises(TrayError, match="StatusNotifierWatcher"):
        with Tray(lambda: None, lambda: None):
            pytest.fail("must not start without watcher")


def test_watcher_restart_registers_the_same_item_again(capsys):
    async def check():
        async with session() as (tray, _client, first, first_bus, _open, _quit):
            service = first.service
            await first_bus.release_name("org.kde.StatusNotifierWatcher")
            for _ in range(100):
                if tray._owner is None:
                    break
                await asyncio.sleep(0.01)
            assert tray._owner is None
            # Repeated absent-watcher polls produce one diagnostic, not a log flood.
            await asyncio.sleep(0.08)
            next_bus, next_watcher = await watcher_bus()
            try:
                assert await asyncio.to_thread(next_watcher.registered.wait, 2)
                assert next_watcher.service == service
            finally:
                disconnect(next_bus)

    asyncio.run(check())
    assert capsys.readouterr().err.count("Desktop tray unavailable") == 1


def test_authentication_timeout_cancels_thread_and_closes_socket(monkeypatch):
    instances = []
    original = module.MessageBus

    def stalled_bus():
        bus = original()
        instances.append(bus)

        async def connect():
            await asyncio.sleep(10)

        bus.connect = connect
        return bus

    monkeypatch.setattr(module, "MessageBus", stalled_bus)
    monkeypatch.setattr(module, "START_TIMEOUT", 0.05)
    tray = Tray(lambda: None, lambda: None)
    with pytest.raises(TrayError, match="timed out starting"):
        tray.__enter__()
    assert not tray._thread.is_alive() and instances[0]._sock.fileno() == -1


def test_closed_tray_cannot_restart_or_dispatch_unknown_action():
    tray = Tray(lambda: None, lambda: None)
    tray.close()
    with pytest.raises(TrayError, match="reused"):
        tray.__enter__()
    with pytest.raises(ValueError, match="unknown tray action"):
        tray._dispatch("something else")


def test_unexpected_runtime_failure_is_visible(capsys):
    tray = Tray(lambda: None, lambda: None)

    async def fail():
        tray._ready.set()
        raise RuntimeError("test bus failure")

    tray._main = fail
    tray._run()
    assert "Desktop tray stopped unexpectedly: test bus failure" in capsys.readouterr().err
