# EPOMAKER Driver for Linux

Independent Linux configuration software for EPOMAKER keyboards, mice and receivers.
**Work in progress. The target is greater than 95% feature parity with the Windows/macOS
3.2.22 installers; that target has not been reached.**

The first implementation is a userspace Python HID backend and CLI for the Glyph/YC3123
protocol. It includes USB/Bluetooth transport code, device discovery, remapping, profiles,
lighting, sleep timers, macros, screen transfer primitives and offline tests. Other model
families, the UI and background features remain in the migration plan.

A catalog entry is not a support claim. The 46 EPOMAKER catalog entries report implementation
and hardware-validation status separately. No model is hardware-verified yet.

## Run

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
# Back up key/Fn maps and settings. Macro bodies and screen images are not included yet.
.venv/bin/epomaker --device /dev/hidrawN backup ./backups/glyph.json
# Read a physical-slot matrix; positions are not HID keycodes.
.venv/bin/epomaker --device /dev/hidrawN matrix --profile 0
```

## Test

```sh
.venv/bin/python -m pytest --cov=epomaker_driver --cov-branch --cov-report=term-missing
.venv/bin/ruff check src tests
.venv/bin/python -m build
```

Tests use fake transports and packet fixtures. Unit-test coverage is not hardware validation
or feature parity. See [migration status](docs/parity.md) and [protocol provenance](docs/provenance.md).

Original implementation code is MIT-licensed. This project does not redistribute the vendor
applications, native executables, bundled JavaScript, logos or UI assets.
