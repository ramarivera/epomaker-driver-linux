# Desktop installation and lifecycle

Install a built wheel into a stable Python 3.11+ virtual environment. The wheel
must include the UI; the source build instructions are in
[control-interface.md](control-interface.md). For the current 0.1.0 build:

```sh
python3 -m venv ~/.local/share/epomaker-driver-linux/venv
~/.local/share/epomaker-driver-linux/venv/bin/python -m pip install ./dist/epomaker_driver_linux-0.1.0-py3-none-any.whl
~/.local/share/epomaker-driver-linux/venv/bin/epomaker desktop-install
```

The application menu entry **EPOMAKER Linux driver** starts the installed Python
environment and opens the local control interface in your default browser.
A terminal remains open for diagnostics and shutdown with Ctrl+C. Closing the
browser tab alone does not stop the driver. Each launch currently creates its
own server on an available port; close the previous terminal before launching
again to avoid competing device connections. Tray controls remain unimplemented. For menu activation that reuses one
background instance, install the user service and use `desktop-install --background`;
see [background service commands](background-service.md).

`desktop-install` writes
`$XDG_DATA_HOME/applications/org.epomaker.DriverLinux.desktop`, defaulting to
`~/.local/share/applications/`. It requires an absolute data directory and
preserves the virtual environment's executable path, including a symlink.
`--data-home /absolute/directory` overrides the launcher directory for each
lifecycle command. The application uses its existing data locations; this
option does not move backups or libraries.

The launcher contains no session token or user credentials. The driver opens
its per-process session URL at runtime. If opening the browser fails, the
terminal reports the failure and retains the URL for manual use. Running
`epomaker serve` without `--open-browser` keeps the existing manual-open behavior.

## Update

Install the chosen new wheel into the same environment with pip's `--upgrade`
option, then rerun `epomaker desktop-install`. That refreshes the owned launcher
and supports moving to a different environment if necessary. Package updates
are explicit; no background updater downloads or installs releases.

```sh
~/.local/share/epomaker-driver-linux/venv/bin/epomaker desktop-status
```

Status reports whether the managed entry exists. It does not test a desktop
session, Python package import, USB access or keyboard compatibility.
Install/update refuses to replace an unrelated file or a symlink at the target
launcher path. Only the entry marked as belonging to this application is managed.

## Uninstall

Remove the launcher before removing the package:

```sh
~/.local/share/epomaker-driver-linux/venv/bin/epomaker desktop-uninstall
~/.local/share/epomaker-driver-linux/venv/bin/python -m pip uninstall epomaker-driver-linux
```

Launcher removal preserves the environment, backup snapshots, macro library,
configuration library and display assets. It neither closes a running server
nor changes USB permissions. Stop any running driver with Ctrl+C first.

The entry follows the [freedesktop Exec specification](https://specifications.freedesktop.org/desktop-entry/latest/exec-variables.html).
Implementation: `src/epomaker_driver/desktop.py`,
`src/epomaker_driver/browser_launch.py`, and `src/epomaker_driver/cli.py`.
