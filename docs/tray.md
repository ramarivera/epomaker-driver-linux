# Desktop tray controls

Run the controls server with a tray icon in a desktop session:

```sh
epomaker serve --tray --open-browser --port 0
```

The keyboard icon offers **Open controls** and **Quit driver**. Opening controls
uses the same server; quitting stops that process and closes its controller,
including active capture and refresh tasks. No keyboard is connected implicitly.
Closing a browser tab leaves the server running. Quitting the server leaves
existing browser tabs open; they can no longer send commands. The driver cannot hide an
independently owned browser window; close the controls tab to hide it.

The tray requires a session D-Bus and a StatusNotifier tray host. It exports
`org.kde.StatusNotifierItem` and a `com.canonical.dbusmenu` menu. No session URL,
HTTP token, or keyboard data is included in its public properties. A missing
host or failed registration is an error when `--tray` was requested; run without
that flag for headless operation. Desktop environments without a compatible
tray host need their own integration before the icon can appear.

After a watcher restart, the running adapter checks for its replacement and
registers the same item again. Loss is reported once per failure period. A changed
session bus may require restarting the driver. Startup cancellation and shutdown
close the owned D-Bus descriptors.

## Background service

To use the tray with the owned user service:

```sh
epomaker service-stop
epomaker service-disable
epomaker service-install --tray
epomaker service-start
epomaker desktop-install --background
# Optional startup in later graphical sessions:
epomaker service-enable
```

Disabling before changing modes removes the old startup target links. Tray-mode
units are ordered after `graphical-session-pre.target`, enabled under
`graphical-session.target`, and stopped with that graphical session. The desktop
must manage those targets and supply a tray host; a lingering user manager alone
is insufficient. Manual `service-start` still requires a desktop session with a
working host. Run the same stop/disable/install sequence without `--tray` to
return to the headless service mode. No service installation or startup setting
is changed merely by installing the Python package.

The [vendor lifecycle audit](releases/glyph-desktop-lifecycle-audit.md) records
remaining differences, including native window hiding and graphical preferences.
Implementation: `src/epomaker_driver/tray.py`, `src/epomaker_driver/cli.py`, and
`src/epomaker_driver/user_service.py`. Regression checks:
`tests/test_tray.py`, `tests/test_tray_cli.py`, and `tests/test_user_service.py`.

Protocol references:
[StatusNotifier specification](https://specifications.freedesktop.org/status-notifier-item/latest-single/),
[KDE interface](https://github.com/KDE/kstatusnotifieritem/blob/master/src/org.kde.StatusNotifierItem.xml),
[Canonical menu XML](https://github.com/gnustep/libs-dbuskit/blob/master/Bundles/DBusMenu/com.canonical.dbusmenu.xml),
and [systemd desktop integration](https://github.com/systemd/systemd/blob/main/docs/DESKTOP_ENVIRONMENTS.md).

## Verification and compatibility

An isolated driver process registered with the development desktop's actual
StatusNotifierWatcher. Its menu and properties were readable, its HTTP connection
remained null, and the Quit menu action exited the process with code 0 and removed
the tray registration. No HID command, firmware operation, or user-unit
installation was performed. Icon appearance and menu placement across desktop
shells remain unverified.

The pinned `dbus-next` 0.2.3 adapter passes current Python 3.14 tests but emits
upstream deprecation warnings for typing/asyncio APIs scheduled for removal in
Python 3.15/3.16. This is a known dependency compatibility limit. Cleanup uses
that pinned version's finalizer and descriptor fields because its public
`disconnect()` shuts down the socket without closing the owned stream/socket.
The tests verify descriptor closure, including cancellation during authentication.
