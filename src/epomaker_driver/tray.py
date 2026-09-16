# ruff: noqa: UP037, F821, F722
"""StatusNotifier tray; protocol references and lifecycle limits are in docs/tray.md."""

import asyncio
import sys
import threading
from collections.abc import Callable
from typing import Any

from dbus_next import Message, PropertyAccess, Variant
from dbus_next.aio import MessageBus
from dbus_next.errors import DBusError
from dbus_next.service import ServiceInterface, dbus_property, method

from .errors import DriverError

START_TIMEOUT = 5.0
CALL_TIMEOUT = 2.0
POLL_INTERVAL = 5.0
_ITEM_PATH = "/StatusNotifierItem"
_MENU_PATH = "/Menu"
_WATCHER = "org.kde.StatusNotifierWatcher"


class TrayError(DriverError):
    """The desktop tray could not be started or stopped cleanly."""


def _error(message: str) -> DBusError:
    return DBusError("com.canonical.dbusmenu.Error", message)


class _Menu(ServiceInterface):
    def __init__(self, activate: Callable[[int], None]) -> None:
        super().__init__("com.canonical.dbusmenu")
        self._activate = activate

    @dbus_property(access=PropertyAccess.READ)
    def Version(self) -> "u":
        return 3

    @dbus_property(access=PropertyAccess.READ)
    def TextDirection(self) -> "s":
        return "ltr"

    @dbus_property(access=PropertyAccess.READ)
    def Status(self) -> "s":
        return "normal"

    @dbus_property(access=PropertyAccess.READ)
    def IconThemePath(self) -> "as":
        return []

    @staticmethod
    def _properties(item_id: int) -> dict[str, Variant]:
        if item_id == 0:
            return {"children-display": Variant("s", "submenu")}
        if item_id not in (1, 2):
            raise _error(f"unknown menu item {item_id}")
        label = "Open controls" if item_id == 1 else "Quit driver"
        return {
            "label": Variant("s", label),
            "enabled": Variant("b", True),
            "visible": Variant("b", True),
        }

    def _filtered(self, item_id, names):
        properties = self._properties(item_id)
        return {key: value for key, value in properties.items() if not names or key in names}

    @method()
    def GetLayout(
        self, parent_id: "i", recursion_depth: "i", property_names: "as"
    ) -> "u(ia{sv}av)":
        if parent_id not in (0, 1, 2) or recursion_depth < -1:
            raise _error("unknown menu node or invalid depth")
        children = []
        if parent_id == 0 and recursion_depth != 0:
            children = [
                Variant("(ia{sv}av)", [item_id, self._filtered(item_id, property_names), []])
                for item_id in (1, 2)
            ]
        return [1, [parent_id, self._filtered(parent_id, property_names), children]]

    @method()
    def GetGroupProperties(self, ids: "ai", property_names: "as") -> "a(ia{sv})":
        return [
            [item_id, self._filtered(item_id, property_names)]
            for item_id in (ids or [0, 1, 2])
            if item_id in (0, 1, 2)
        ]

    @method()
    def GetProperty(self, item_id: "i", name: "s") -> "v":
        properties = self._properties(item_id)
        if name not in properties:
            raise _error(f"unknown menu property {name}")
        return properties[name]

    @method()
    def Event(self, item_id: "i", event_id: "s", data: "v", timestamp: "u") -> None:
        if item_id not in (0, 1, 2):
            raise _error(f"unknown menu item {item_id}")
        if item_id and event_id == "clicked":
            self._activate(item_id)

    @method()
    def EventGroup(self, events: "a(isvu)") -> "ai":
        invalid = []
        for item_id, event_id, _data, _timestamp in events:
            if item_id not in (0, 1, 2):
                invalid.append(item_id)
            elif item_id and event_id == "clicked":
                self._activate(item_id)
        return invalid

    @method()
    def AboutToShow(self, item_id: "i") -> "b":
        if item_id not in (0, 1, 2):
            raise _error(f"unknown menu node {item_id}")
        return False

    @method()
    def AboutToShowGroup(self, ids: "ai") -> "aiai":
        return [[], [item_id for item_id in ids if item_id not in (0, 1, 2)]]


class _StatusNotifierItem(ServiceInterface):
    def __init__(self, menu: str, dispatch: Callable[[str], None]) -> None:
        super().__init__("org.kde.StatusNotifierItem")
        self._menu = menu
        self._dispatch = dispatch

    @dbus_property(access=PropertyAccess.READ)
    def Category(self) -> "s":
        return "Hardware"

    @dbus_property(access=PropertyAccess.READ)
    def Id(self) -> "s":
        return "epomaker-driver"

    @dbus_property(access=PropertyAccess.READ)
    def Title(self) -> "s":
        return "EPOMAKER Linux driver"

    @dbus_property(access=PropertyAccess.READ)
    def Status(self) -> "s":
        return "Active"

    @dbus_property(access=PropertyAccess.READ)
    def WindowId(self) -> "i":
        return 0

    @dbus_property(access=PropertyAccess.READ)
    def IconName(self) -> "s":
        return "input-keyboard"

    @dbus_property(access=PropertyAccess.READ)
    def IconPixmap(self) -> "a(iiay)":
        return []

    @dbus_property(access=PropertyAccess.READ)
    def OverlayIconName(self) -> "s":
        return ""

    @dbus_property(access=PropertyAccess.READ)
    def OverlayIconPixmap(self) -> "a(iiay)":
        return []

    @dbus_property(access=PropertyAccess.READ)
    def AttentionIconName(self) -> "s":
        return ""

    @dbus_property(access=PropertyAccess.READ)
    def AttentionIconPixmap(self) -> "a(iiay)":
        return []

    @dbus_property(access=PropertyAccess.READ)
    def AttentionMovieName(self) -> "s":
        return ""

    @dbus_property(access=PropertyAccess.READ)
    def ToolTip(self) -> "(sa(iiay)ss)":
        return ["input-keyboard", [], "EPOMAKER Linux driver", "Open controls or quit driver"]

    @dbus_property(access=PropertyAccess.READ)
    def ItemIsMenu(self) -> "b":
        return False

    @dbus_property(access=PropertyAccess.READ)
    def Menu(self) -> "o":
        return self._menu

    @dbus_property(access=PropertyAccess.READ)
    def IconThemePath(self) -> "s":
        return ""

    @method()
    def Activate(self, x: "i", y: "i") -> None:
        self._dispatch("open")

    @method()
    def SecondaryActivate(self, x: "i", y: "i") -> None:
        self._dispatch("open")

    @method()
    def ContextMenu(self, x: "i", y: "i") -> None:
        pass

    @method()
    def Scroll(self, delta: "i", orientation: "s") -> None:
        pass


class Tray:
    """Own one session-bus connection and a cancellable background event loop."""

    def __init__(self, open_callback: Callable[[], Any], quit_callback: Callable[[], Any]):
        self._open_callback = open_callback
        self._quit_callback = quit_callback
        self._thread = None
        self._loop = None
        self._task = None
        self._bus = None
        self._owner = None
        self._ready = threading.Event()
        self._startup_error = None
        self._closed = False

    def __enter__(self):
        if self._thread is not None or self._closed:
            raise TrayError("tray context cannot be reused")
        self._thread = threading.Thread(target=self._run, name="epomaker-tray", daemon=True)
        self._thread.start()
        if not self._ready.wait(START_TIMEOUT):
            self.close()
            raise TrayError("timed out starting the desktop tray")
        if self._startup_error is not None:
            error = self._startup_error
            self.close()
            raise TrayError(f"cannot start desktop tray: {error}") from error
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self._closed = True
        if self._loop is not None and self._task is not None and not self._loop.is_closed():
            try:
                self._loop.call_soon_threadsafe(self._task.cancel)
            except RuntimeError:
                # The event loop can finish between is_closed and scheduling.
                pass
        if self._thread is not None:
            self._thread.join(START_TIMEOUT)
            if self._thread.is_alive():
                raise TrayError("timed out stopping the desktop tray")

    def _dispatch(self, action):
        if action not in ("open", "quit"):
            raise ValueError("unknown tray action")
        callback = self._open_callback if action == "open" else self._quit_callback
        threading.Thread(target=callback, name=f"epomaker-tray-{action}", daemon=True).start()

    def _run(self):
        try:
            asyncio.run(self._main())
        except asyncio.CancelledError:
            pass
        except Exception as error:
            self._startup_error = error
            if self._ready.is_set():
                print(f"Desktop tray stopped unexpectedly: {error}", file=sys.stderr)
        finally:
            self._ready.set()

    async def _rpc(self, **kwargs):
        response = await asyncio.wait_for(self._bus.call(Message(**kwargs)), CALL_TIMEOUT)
        if response is None or response.error_name:
            name = response.error_name if response is not None else "no response"
            raise TrayError(f"desktop tray request failed: {name}")
        return response.body

    async def _owner_name(self):
        return (
            await self._rpc(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="GetNameOwner",
                signature="s",
                body=[_WATCHER],
            )
        )[0]

    async def _register(self, owner):
        host = await self._rpc(
            destination=owner,
            path="/StatusNotifierWatcher",
            interface="org.freedesktop.DBus.Properties",
            member="Get",
            signature="ss",
            body=[_WATCHER, "IsStatusNotifierHostRegistered"],
        )
        if not host or host[0].signature != "b" or host[0].value is not True:
            raise TrayError("no StatusNotifier tray host is registered")
        await self._rpc(
            destination=owner,
            path="/StatusNotifierWatcher",
            interface=_WATCHER,
            member="RegisterStatusNotifierItem",
            signature="s",
            body=[self._bus.unique_name],
        )
        self._owner = owner

    async def _main(self):
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.current_task()
        if self._closed:
            return
        try:
            self._bus = MessageBus()
            await asyncio.wait_for(self._bus.connect(), CALL_TIMEOUT)
            self._bus.export(
                _MENU_PATH,
                _Menu(lambda item_id: self._dispatch("open" if item_id == 1 else "quit")),
            )
            self._bus.export(_ITEM_PATH, _StatusNotifierItem(_MENU_PATH, self._dispatch))
            try:
                await self._register(await self._owner_name())
            except Exception as error:
                raise TrayError(
                    "StatusNotifierWatcher or tray host is unavailable; start a desktop tray host or omit --tray"
                ) from error
            self._ready.set()
            warned = False
            while True:
                await asyncio.sleep(POLL_INTERVAL)
                try:
                    owner = await self._owner_name()
                    if owner != self._owner:
                        await self._register(owner)
                    warned = False
                except (TrayError, OSError, TimeoutError, EOFError):
                    self._owner = None
                    if not warned:
                        print(
                            "Desktop tray unavailable; waiting for its watcher. Restart the driver if the session bus changed.",
                            file=sys.stderr,
                        )
                        warned = True
        finally:
            if self._bus is not None:
                # dbus-next 0.2.3 disconnect shuts down but does not close the
                # socket/stream, and authentication may not have installed a
                # reader yet. Finalize before closing both owned descriptors.
                self._bus.disconnect()
                self._bus._finalize()
                try:
                    self._bus._stream.close()
                finally:
                    self._bus._sock.close()
