# Configuration snapshots and recovery

`backup` writes a version 2 JSON snapshot. It captures all three normal matrices,
Windows/Mac Fn matrices, every macro referenced by those matrices, main/side lighting
configuration, sleep timers, active profile, debounce, keyboard options and automatic
OS selection. Unknown four-byte key actions and unrelated keyboard-option bytes are
preserved. Files are atomically created with user-only permissions.

Screen pixels, custom RGB picture contents and unreferenced macro slots are not captured
by an ordinary backup. These omissions are recorded in the file. A snapshot is not a
firmware image or a complete device-memory dump. The current importer can inspect vendor
JSON/raw-DEFLATE files but restoration accepts this project's version 2 schema only.
Earlier version 1 snapshots can still be inspected; create a new backup before restoring.

```sh
epomaker --device /dev/hidrawN backup saved.json
epomaker --device /dev/hidrawN restore saved.json --backup before-restore.json
```

Restore validates every field and referenced macro before device writes. It identifies
the device, captures its current configuration and any additional macro slots about to
be overwritten, and saves the recovery file before mutation. The recovery path must not
already exist; failure to save aborts the operation. Neither the source snapshot nor an
existing recovery file is overwritten.

Macro storage is restored before key bindings. Normal matrices, Fn matrices, lighting,
options and timers follow; active profile selection is last. Every section is read back.
Fn restoration changes only slots that differ. Macro writes include trailing zeroes to
clear data left by a longer previous macro.

Firmware changes are not atomic. A failed readback or disconnect stops restoration and
reports that the device may be partially changed, with the recovery file path. After
resolving the connection issue, restoring that recovery snapshot uses the same command
with a different new `--backup` path. No automatic reconnect or rollback is attempted.

These operations have simulated-firmware tests, including restoration and recovery in
both directions, invalid inputs, preexisting recovery files, dropped writes and macro
replacement. They remain unverified on physical hardware.
