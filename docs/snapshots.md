# Configuration snapshots and recovery

`backup` writes a version 3 JSON snapshot for Glyph, version 4 for RT85/RT75,
version 5 for RY6602, or schema version 6 for RT100/Dynatab75X-UK. It captures
all three Glyph/RT75 or four RT85 normal matrices,
Windows/Mac Fn matrices, all 256 macro slots for Glyph (referenced macros for the
other modern models), main/side lighting
configuration, sleep timers, active profile, debounce, keyboard options and automatic
OS selection, plus all five custom RGB pictures. Unknown four-byte key actions and unrelated keyboard-option bytes are
preserved. Files are atomically created with user-only permissions.

Screen pixels are not captured. Non-Glyph ordinary backups also omit unreferenced
macro slots. These omissions are recorded in the file. A snapshot is not a
firmware image or a complete device-memory dump. The current importer can inspect vendor
JSON/raw-DEFLATE files but restoration accepts this project's version 2, 3, 4, 5 and 6 schemas.
Restoring version 2 leaves custom RGB pictures unchanged and reports that limitation.
Earlier version 1 snapshots can still be inspected; create a new backup before restoring.

Glyph capture includes empty and undecodable raw macro slots. Restoring a complete
Glyph backup restores all 256 slots, including clearing slots that were empty in
the saved state. Older partial version 2/3 backups remain accepted: omitted macro
slots are left unchanged, and the pre-restore recovery copy captures all 256 slots.

## YC3121 schema version 6

RT100 and Dynatab75X-UK backups use schema version 6. They contain all three normal
512-byte maps, the migrated Fn layer 0 map, referenced macros plus incoming macro
slots, custom picture 0, validated raw main-light fields, four sleep timers,
debounce, automatic OS selection and the active profile. Restore validates the
complete snapshot, identifies the connected model, saves an atomic no-clobber
recovery copy, then verifies every write and selects the active profile last.

Manual OS options are excluded because the older vendor setter has ambiguous
semantics. Screen pixels, unreferenced macros and independent OS-specific Fn banks
are also excluded; the snapshot records these limitations and does not claim that
Fn layer 0 is separate Windows and Mac storage.

```sh
epomaker --device /dev/hidrawN backup saved.json
epomaker --device /dev/hidrawN restore saved.json --backup before-restore.json
```

Restore validates every field and referenced macro before device writes. It identifies
the device and rejects a different model, captures its current configuration and any additional macro slots about to
be overwritten, validates that recovery snapshot, and saves it before mutation. The recovery path must not
already exist; failure to save aborts the operation. Neither the source snapshot nor an
existing recovery file is overwritten.

Macro storage is restored before key bindings. Normal matrices, Fn matrices, lighting,
options and timers follow; active profile selection is last. Every section is read back.
Fn restoration changes only slots that differ. Custom RGB pictures include 126 writable
color slots; six additional bytes returned by the read protocol are excluded because
the vendor's writer does not address them. Macro writes include trailing zeroes to
clear data left by a longer previous macro.

Firmware changes are not atomic. A failed readback or disconnect stops restoration and
reports that the device may be partially changed, with the recovery file path. After
resolving the connection issue, restoring that recovery snapshot uses the same command
with a different new `--backup` path. No automatic reconnect or rollback is attempted.

These operations have simulated-firmware tests, including restoration and recovery in
both directions, invalid inputs, preexisting recovery files, dropped writes and macro
replacement. They remain unverified on physical hardware.

## Factory reset

```sh
epomaker --device /dev/hidrawN factory-reset --backup before-reset.json
```

This explicitly resets device configuration. Before sending the reset command, the
CLI captures all normal/Fn maps, settings, custom colors, and **all 256 macro slots**,
including unreferenced slots. It atomically saves a private recovery snapshot and
refuses to overwrite an existing file. A failed capture or save prevents the reset.
Screen pixels cannot currently be read back and are not recoverable from this file.

The implementation sends one checksum-protected command `01 00 00 00 00 00 00 fe`
followed by 56 zero bytes and waits two seconds. This follows `reset(true)` in the
recovered YC3123 keyboard base (`623d2d52.js`, lines 140–148). It does not flash firmware.
A successful host write returns `reset_sent: true` and
`factory_defaults_verified: false`. Cached identity is discarded after the attempt,
so the next operation must identify the device again. A disconnect or write error
reports that the reset outcome is unknown and includes the existing recovery path;
the command never retries a possibly completed reset automatically.

Reconnect and inspect the physical keyboard after resetting. Use `restore` with the
saved file and another new recovery path if you want to put the saved configuration
back. Factory behavior, which device memories are reset, and reconnect timing remain
hardware-unverified. This operation is currently available through the CLI.


## RT85 schema version 4

RT85 snapshots carry internal model ID 2895 and exactly four 512-byte normal
matrices. Both Fn maps, all five custom RGB pictures, referenced macros, sleep,
lighting and OS settings are preserved. Debounce is explicitly `null` because
that control is not migrated for RT85; restoration never sends its setter.
RT85 side mode/speed validation honors its five effects and wave maximum of 4.

Versions 2 and 3 remain Glyph-only. Version 4 also accepts Glyph snapshots with
three matrices and a numeric debounce value. A matching model ID is mandatory
at restoration time; neither direction of Glyph/RT85 cross-restoration is allowed.
The current device's identity is read again even if the caller cached one earlier.
Malformed input fails before writes or recovery-file creation. Invalid current
state that cannot be restored prevents destructive reset or restoration as well.

Factory reset uses the same inherited YC3123 opcode `01` and two-second wait on
both models (shared protocol `623d2d52.js`, `reset`, lines 140–149). RT85 reset
captures four profiles and all 256 macro slots. Its saved snapshot is validated
before the reset command. As with Glyph, `reset_sent` does not prove factory
state, reconnect behavior or screen-image recovery.


## RT75 recovery without side lighting

RT75 uses schema version 4 with three normal matrices, actual Windows/Mac Fn
matrices, numeric debounce and `side_light: null`. Capturing and restoring this
model never query or write side-light state. A non-null side-light section is
rejected before any writes. Full configuration recovery uses the bytes read from
the keyboard, independently of the vendor Mac-default naming discrepancy.

All four sleep timers are validated against the same model data used for direct
writes. RT75 values outside 60–3600 seconds are rejected before creating the
recovery file. Glyph and RT85 retain their wider limits. A recovery capture with
invalid timer values also prevents a restore or factory reset.

RT75 reset uses the inherited YC3123 `01` command after saving and validating all
three profiles, both Fn maps, five RGB pictures, settings and all 256 macro slots.
The reset result continues to distinguish a sent command from verified factory
state. Cross-model restores between any pair of Glyph, RT85 and RT75 are rejected.


## RY6602 schema version 5

SN020, EK75, TH80 V3 MAX, TH80 V2 and TH65 Max require version 5. Profile counts
come from each model: four for SN020 and three for the others. Side lighting is
null for SN020/EK75; other RY6602 models accept their wave/snake/breathing/off
layout with speed at most 3. Raw model-specific color flags are preserved.

Sleep data contains exactly `bluetooth`, `dongle` and `deep_bluetooth`. Restoration
uses the preserving three-timer setter, leaving the device's current unexposed
receiver field intact. That field and screen pixels are not recoverable from
these snapshots. The limitation is present in the returned metadata. Reset saves
all 256 macros, validates the snapshot, and sends the shared reset opcode only
after the private recovery file exists. See [ry6602.md](ry6602.md) for commands.

## Magnetic schema 7

All fourteen migrated magnetic models have a separate [schema 7](he-recovery.md)
with per-profile submodes and full raw magnetic state. It includes every macro
slot and requires identical model and firmware versions for USB restoration.
