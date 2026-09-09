# EPOMAKER Driver for Linux

Independent Linux configuration software for EPOMAKER keyboards, mice and receivers.
**Work in progress. The next release is Glyph v1: complete management of the
EPOMAKER Glyph on Linux, referenced against the Windows/macOS 3.2.22 installers.
That release is not complete. Other products are deferred from v1.**

The [Glyph v1 scope and release checklist](docs/releases/glyph-v1.md) is the active
release plan. The broader backend inventory below records existing work; it is not
the v1 completion target.

The first implementation is a userspace Python HID backend, CLI and local React control
interface for the Glyph/YC3123 protocol. It includes USB/Bluetooth transport code, device discovery, remapping, profiles,
lighting, sleep timers, macros, screen transfer primitives and offline tests. Other model
families and background features remain in the migration plan.

[RT85 support](docs/rt85.md) is also available through the CLI: four normal
profiles, Windows/Mac Fn layers, macros, sleep timers, its 320×172 display,
main/side lighting, custom RGB pictures, OS options, snapshots and factory reset
with a recovery copy. Its graphical interface remains unfinished.

[RT75 support](docs/rt75.md) adds three profiles, both Fn layers, macros, sleep
timers, debounce, OS options, main lighting, its 240×240 display, snapshots and
reset with recovery through the CLI.

[RT100 PRO support](docs/rt100pro.md) adds the three-profile YC3123 backend:
normal and Windows/Mac Fn maps, macros, sleep/debounce and OS settings, shared
RGB lighting, snapshots/reset, and its five-bank 240×240 RGB565 display. The
catalog omits display memory, so the installer drawing-board default of 7 MiB
limits animations to 56 frames.

[RY6602 core support](docs/ry6602.md) covers SN020, EK75, TH80 V3 MAX, TH80 V2
and TH65 Max: keymaps, Fn layers, macros, profiles, three sleep timers, debounce
and OS controls, lighting and custom RGB pictures. SN020, TH80 V3 MAX and TH65
Max also support RGB24 still images and animations. All five have configuration
backup, restore and reset with recovery copies.

[Older YC3121 support](docs/yc3121.md) adds RT100 and Dynatab75X-UK over USB:
normal keymaps, three profiles, migrated Fn layer 0 addressing, macros, main lighting, one writable
custom RGB picture, sleep timers, debounce, automatic OS selection and direct USB display
workflows. Schema 6 backup and restore covers their migrated configuration; OS-specific Fn
banks, manual OS options and screen pixels remain outside recovery. The GUI still supports
Glyph only.

[HE60 Lite support](docs/he60-lite-research.md) adds both USB variants:
two normal profiles with four submodes each, Windows/Mac Fn maps, macros,
profile selection, magnetic-parameter reads and per-key actuation/rapid-trigger
settings with readback, OS controls, 21 main-light effects and custom RGB pictures.
Debounce is wired-only; three sleep timers are wireless-only. Magnetic mode
definitions include DKS, tap/hold and toggle actions, plus reciprocal snap
pairing and removal. [Schema 7 recovery](docs/he-recovery.md) includes all profiles,
magnetic fields and all 256 macros, with exact firmware matching.

[RY5088 H60 support](docs/ry5088-h60.md) adds internal ID 3662 over USB:
four profiles with four normal submodes each, Windows/Mac Fn maps, macros,
OS controls, main lighting and five custom pictures. Magnetic controls use
firmware-dependent 0.1, 0.01 or 0.005 mm steps. [HE68 Lite variants](docs/ry5088-he68.md) additionally enable IDs 2762, 2883
and 3664, including lossless switch-type reads and selection. Other same-PID siblings remain gated.
[Four additional wired RY5088 models](docs/ry5088-wired.md) add HE68 Mag,
KIIBOOM-68C, Epomaker 65 and HE60 Wired, with model-specific Fn and side lighting.
The [four wireless-capable RY5088 additions](docs/ry5088-wireless.md) support USB
configuration, including their three sleep timers and RF version handling.

[HE60 model 3746](docs/ry5088-he60.md) adds its own matrices, 3.4 mm travel limit
and 云玉磁轴/天青轴 switch selection. [HE108 ID 3365](docs/ry5088-he108.md) has enabled partial USB support with four
profiles, side lighting, magnetic controls, and model-specific sleep/travel limits;
hardware remains unverified.

[G84 HE Pro](docs/g84-he-pro.md) adds its code-133 switch, catalog travel/deadzone
limits and sleep settings through the USB backend.

[HE65 V2](docs/he65-v2.md) adds internal ID 3417 with four profiles, Fn maps,
magnetic configuration, main lighting, pictures, normal 24G/Bluetooth sleep
timers, seven catalog switch types and three normal-layer knob bindings.
Hardware remains unverified.

[HE75 V2](docs/he75-v2.md) adds IDs 3518 and 3883 with model-specific profile
counts, four-effect `ei` side lighting, magnetic configuration, canonical switch
codes, knob bindings and USB sleep settings. Hardware remains unverified.

[HE75 Mag](docs/he75-mag.md) adds internal ID 2520 with four profiles, a
Windows-only Fn matrix, seven canonical switch codes, magnetic mode/snap
configuration, main lighting, and generic USB sleep controls. Hardware remains
unverified.

[HE65 Mag](docs/he65-mag.md) adds internal ID 2376 with four profiles, Windows/Mac Fn matrices, magnetic configuration, five-bank 128×128 RGB565 display support, clock/language controls, and knob-aware restrictions. Switch-type writes are disabled by the catalog; USB hardware remains unverified.

[HE75 V2 TMR model 3613](docs/he75-tmr-3613.md) adds the two-profile TMR
variant, with its four-switch catalog, travel limits and side lighting.

All twenty-three implemented magnetic IDs support a [timed USB calibration session](docs/calibration.md)
with raw telemetry and cleanup on errors or Ctrl-C. Physical calibration results
have not been verified.

A catalog entry is not a support claim. The 46 EPOMAKER catalog entries report implementation
and hardware-validation status separately. No model is hardware-verified yet.

[Five CH585 mice](docs/ch585-protocol.md) now support USB identification, eight
profiles, named/raw button mappings, 50 macro slots, DPI-level editing, report-rate selection, sleep/
debounce/scroll timing, model-gated sensor settings and
[configuration backup/restore](docs/mouse-recovery.md).
Mouse commands use their own protocol and are rejected on keyboards.

## Run

For the graphical interface, follow the [build and launch instructions](docs/control-interface.md).
The Glyph Lighting page includes [live screen lighting](docs/live-lighting.md)
on wired USB firmware that advertises support; the Display page offers
[continuous host statistics](docs/system-info.md). Physical output remains unverified.
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
# Back up Glyph key/Fn maps, all 256 macro slots, and settings.
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
# Export a custom RGB picture as model-sized six-digit color strings (126 or 128 slots).
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
or feature parity. See [migration status](docs/parity.md), [model inventory](docs/model-inventory.md)
and [protocol provenance](docs/provenance.md).
The [Glyph protocol reference](docs/glyph-protocol.md) documents recovered packet layouts
and unresolved behavior for contributors.

Original implementation code is MIT-licensed. This project does not redistribute the vendor
applications, native executables, bundled JavaScript, logos or UI assets.
