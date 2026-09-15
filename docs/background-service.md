# Background driver service

The optional systemd **user** service runs one loopback server for the current
login session. Install the wheel in a stable Python environment first, as shown
in [desktop installation](desktop-installation.md), then run:

```sh
epomaker service-install
epomaker service-start
epomaker service-open
epomaker service-status
```

`service-open` opens the running server in your browser; it does not start a
second server. It also prints the URL in your invoking terminal for manual use
if the browser cannot open; this output is not produced by the background unit.
`service-start` asks systemd to start the same unit and is
idempotent while it is running. It does not connect a keyboard or restore an old
stream. Wait for the service to start before opening it; an unavailable socket
produces an error and can be retried. Closing the browser leaves the service
running. `service-status` returns systemd's load, active, and substate fields,
including inactive/failed states.

Installation writes the marker-owned unit at
`$XDG_CONFIG_HOME/systemd/user/epomaker-driver-linux.service`, defaulting to
`~/.config/systemd/user/`. `--config-home` overrides that location for install
and uninstall; systemd must actually search that configured user-unit directory
for start/stop to manage the same unit. The existing executable symlink is kept,
so virtual environments work. Paths with spaces, dollar signs, and percent signs
are supported; quotes, backslashes, and control characters in the executable
path are rejected because the generated systemd executable field cannot safely
represent them with this implementation.

The server uses a random port and keeps its session token in memory. A private
mode-0600 Unix socket under `$XDG_RUNTIME_DIR/epomaker-driver-linux/` provides the
activation URL to this user. The directory must be user-owned and mode 0700.
Neither the unit nor a regular file stores the token. Standard output is disabled
for the service so the URL does not enter the journal. Diagnostic stderr remains
available through `journalctl --user -u epomaker-driver-linux.service`.

## Stop, update, and remove

```sh
epomaker service-stop
# Install your chosen replacement wheel, then:
epomaker service-install
epomaker service-start
# To remove the user unit:
epomaker service-uninstall
```

Stop before changing the installed package. SIGINT allows the server to close
its controller, stop capture/refresh tasks, and remove its socket. systemd removes
the runtime directory when the unit stops. It does not restart after a crash or
automatically replay keyboard writes. If graceful shutdown exceeds 15 seconds,
systemd may terminate remaining processes. User backups and libraries survive
unit removal. A daemon-reload failure leaves the saved unit in place and reports
that partial installation; retry after restoring access to the user manager.
Uninstall stops the service before removing the owned unit and reloads the
manager. Unrelated files and symlinks at the unit path are refused.

This is explicitly started service support. Login autostart, tray controls,
service-backed application-menu activation, suspend/resume restoration, and
physical device lifecycle verification remain unfinished. The existing desktop
menu entry still starts a foreground server; use either that workflow or these
service commands to avoid competing instances. Systems without a working systemd
user manager can continue to use `epomaker serve --open-browser`.

## Verification

The generated unit passed installed `systemd-analyze --user verify`, including
an executable symlink with spaces, `$`, and `%`. An isolated foreground process
published its private socket, then exited with code 130 after SIGINT, removed
the socket, and emitted no session token to stdout/stderr. No user unit was
installed or started during development, and no HID command was sent.

Implementation: `src/epomaker_driver/user_service.py`,
`src/epomaker_driver/control_socket.py`, and `src/epomaker_driver/cli.py`.
Regression tests: `tests/test_user_service.py` and `tests/test_control_socket.py`.
