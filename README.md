# EPOMAKER Driver for Linux

Independent Linux configuration software for EPOMAKER keyboards, mice and receivers.
**Work in progress. The target is greater than 95% feature parity with the Windows/macOS
3.2.22 installers; that target has not been reached.**

The first implementation is a userspace Python HID backend, CLI and local React control
interface for the Glyph/YC3123 protocol. It includes USB/Bluetooth transport code, device discovery, remapping, profiles,
lighting, sleep timers, macros, screen transfer primitives and offline tests. Other model
families and background features remain in the migration plan.

[RT85 support](docs/rt85.md) is also available through the CLI: four normal
profiles, Windows/Mac Fn layers, macros, sleep timers and its 320×172 display.
Lighting and other unverified RT85 settings remain disabled.

A catalog entry is not a support claim. The 46 EPOMAKER catalog entries report implementation
and hardware-validation status separately. No model is hardware-verified yet.

## Run

For the graphical interface, follow the [build and launch instructions](docs/control-interface.md).
Run `epomaker serve`, open its printed session URL, and select the discovered keyboard.


```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/epomaker discover
.venv/bin/epomaker models
.venv/bin/epomaker --device /dev/hidrawN identify
.venv/bin/epomaker --device /dev/hidrawN status
```

Use the command collection reported by `discover`, not a hardcoded hidraw number. Discovery
reads sysfs metadata only. All other device commands require an explicitly selected path.
Device access may require [permissions](docs/hardware.md).

```sh
# Write a visible RGB setting, then read it back.
.venv/bin/epomaker --device /dev/hidrawN light solid --rgb ff8040
# Back up key/Fn maps, referenced macros, and settings.
.venv/bin/epomaker --device /dev/hidrawN backup ./backups/glyph.json
# Restore after saving the current configuration to a new recovery file.
.venv/bin/epomaker --device /dev/hidrawN restore ./backups/glyph.json --backup ./backups/before-restore.json
# Reset configuration only after saving a new recovery snapshot.
.venv/bin/epomaker --device /dev/hidrawN factory-reset --backup ./backups/before-reset.json
# Select the Mac Fn layer or automatic OS selection.
.venv/bin/epomaker --device /dev/hidrawN options --system mac
.venv/bin/epomaker --device /dev/hidrawN auto-os on
# Read a physical-slot matrix; positions are not HID keycodes.
.venv/bin/epomaker --device /dev/hidrawN matrix --profile 0
# Upload a still PNG/JPEG; preserve aspect ratio with black borders.
.venv/bin/epomaker --device /dev/hidrawN screen wallpaper.png --fit
.venv/bin/epomaker --device /dev/hidrawN animation wallpaper.gif --fit
# Write a keyboard macro, then verify all 256 bytes by reading it back.
.venv/bin/epomaker --device /dev/hidrawN macro 0 macro.json
.venv/bin/epomaker --device /dev/hidrawN get-macro 0
# Export a custom RGB picture as 126 six-digit color strings.
.venv/bin/epomaker --device /dev/hidrawN get-picture 0 > colors.json
# Import and activate that picture, or change one physical RGB slot.
.venv/bin/epomaker --device /dev/hidrawN picture 0 colors.json --activate
.venv/bin/epomaker --device /dev/hidrawN picture-key 0 10 ff8040
# Inspect host statistics or refresh the display a fixed number of times.
.venv/bin/epomaker host-info
.venv/bin/epomaker --device /dev/hidrawN system-info --count 20 --interval 3
```

Macro JSON contains `repeat` and `events`. Each event has `hid_usage`, boolean `down`,
and `delay_ms` (1–65535). For example:

```json
{"repeat":1,"events":[{"hid_usage":4,"down":true,"delay_ms":10},{"hid_usage":4,"down":false,"delay_ms":10}]}
```

Assigning a macro to a key is a separate remapping operation. Use `bind-macro`,
`bind-key`, `bind-media`, `bind-mouse`, and `disable-key` for named actions. Macro files
also support mouse-button and movement events; `get-macro --decoded` exports editable
JSON. See [macro and binding commands](docs/macros.md).

Still images are converted
to the display's column-major RGB565 format. The `animation` command accepts 2–46
frames with the vendor's averaged frame timing. See [display behavior](docs/display.md).
See [snapshot behavior](docs/snapshots.md) for included settings, exclusions, and recovery.
See [system-information collection](docs/system-info.md) for units and sensor selection.

## Test

```sh
.venv/bin/python -m pytest --cov=epomaker_driver --cov-branch --cov-report=term-missing
.venv/bin/ruff check src tests
.venv/bin/python -m build
```

Tests use fake transports and packet fixtures. Unit-test coverage is not hardware validation
or feature parity. See [migration status](docs/parity.md) and [protocol provenance](docs/provenance.md).
The [Glyph protocol reference](docs/glyph-protocol.md) documents recovered packet layouts
and unresolved behavior for contributors.

Original implementation code is MIT-licensed. This project does not redistribute the vendor
applications, native executables, bundled JavaScript, logos or UI assets.
