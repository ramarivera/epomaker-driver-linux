# Local control interface

The React interface exposes the implemented Glyph driver through a loopback Python
server. It supports keymaps and Fn layers, lighting and custom color slots, editable
macros, still/animated images, clock/statistics, settings, and configuration backups.
Lighting controls follow each Glyph effect's brightness, speed, RGB/rainbow and
option metadata. Music and screen-color effects identify the missing host-input
service. Settings omits the vendor-inapplicable debounce control; restoring an older
backup reports that its legacy debounce value was skipped.
Custom colors supports offline pattern creation, painting, fill, and validated
JSON import/export. See [Glyph pattern files and bank selection](glyph-patterns.md).
All device support and hardware-validation limits in [parity.md](parity.md) apply.

## Build and run

Requires Python 3.11+ and Node.js 22.12+ (Node 24 is used in CI).

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
npm ci --prefix ui
npm run build --prefix ui
.venv/bin/epomaker serve
```

Open the URL printed by the command. Its fragment contains a per-process session
token. Select the discovered command device and press Connect. Offline preview allows
local editing but disables device writes. Device permissions are documented in
[hardware.md](hardware.md). The server does not elevate privileges or install rules.

`serve --port 0` chooses an available port; the default is 8932. Ctrl+C closes the
server and its keyboard connection. Recovery files default to
`~/.local/state/epomaker-driver-linux/backups`; change this with `--backup-dir`.
The named macro library defaults to `~/.local/share/epomaker-driver-linux/macros`;
change this independently with `--library-dir`. Library operations are available
offline and persist across browser/server restarts. See
[library and device-slot semantics](macros.md#named-macro-library).
A successful restore displays the recovery path. Downloaded backups go through the
browser's normal download flow. Glyph backups include all 256 macro slots, including
unreferenced and empty slots. Screen pixels are not included.

Backups also provides a Glyph factory-reset action with an explicit acknowledgement.
It saves a private recovery file before sending the command, then drops the connection
even if the operation fails. Reconnect through the device selector before inspecting
or restoring settings. A sent command does not prove factory defaults; failed writes
report an unknown outcome and the recovery path. The driver never retries reset.

The server binds only to 127.0.0.1, checks Host and Origin, and requires a token header
for every API operation. It accepts bounded JSON bodies, confines static assets to the
built UI directory, and never accepts arbitrary device or recovery paths from the
browser. Share neither the session URL nor its token. Opening multiple tabs controls
the same connection; requests are serialized, but unsaved edits are local to each tab.

## Development and verification

The frontend build is generated into `src/epomaker_driver/web`, excluded from git, and
included in Python distributions when built before `python -m build`. Building a wheel
without first building the UI produces a CLI-only package; the server reports missing
assets with build instructions. CI builds the UI before packaging on every Python version.

```sh
.venv/bin/pytest --cov=epomaker_driver --cov-branch --cov-fail-under=98
npx --prefix ui playwright install chromium
npm test --prefix ui
```

The browser suite launches `tests/serve_ui.py`, whose only device is explicitly named
Glyph simulator. All packets stay in simulated firmware; it never opens hidraw. The
fixed token in that harness is test-only. Automated workflows cover main/Fn assignment,
lighting, custom patterns, macro editing and malformed imports, image upload, settings,
backup/restore, and a narrow viewport. They complement protocol tests and manual visual
verification through the Codex in-app browser. See [design/spec.md](design/spec.md).

The Macro page includes focused keyboard and mouse-button recording with measured/fixed delays and
an explicit draft review before replacement. See [macro recording](macros.md#focused-input-recording)
for reserved shortcuts and capture limitations.

Remaining interface work includes localization, native packaging,
reactive host lighting, background refresh, and richer display controls. Additional
keyboard models and unrelated protocol families are deferred under the
[Glyph-only v1 scope](releases/glyph-v1.md). A successful simulated readback does not
establish hardware parity.
