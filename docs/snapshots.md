# Configuration snapshots and recovery

`backup` writes a version 3 JSON snapshot for Glyph or version 4 for RT85. It captures
all three Glyph or four RT85 normal matrices,
Windows/Mac Fn matrices, every macro referenced by those matrices, main/side lighting
configuration, sleep timers, active profile, debounce, keyboard options and automatic
OS selection, plus all five custom RGB pictures. Unknown four-byte key actions and unrelated keyboard-option bytes are
preserved. Files are atomically created with user-only permissions.

Screen pixels and unreferenced macro slots are not captured
by an ordinary backup. These omissions are recorded in the file. A snapshot is not a
firmware image or a complete device-memory dump. The current importer can inspect vendor
JSON/raw-DEFLATE files but restoration accepts this project's version 2, 3 and 4 schemas.
Restoring version 2 leaves custom RGB pictures unchanged and reports that limitation.
Earlier version 1 snapshots can still be inspected; create a new backup before restoring.

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
