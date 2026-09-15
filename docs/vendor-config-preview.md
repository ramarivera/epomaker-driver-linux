# Inspecting a vendor Glyph configuration

`epomaker preview-vendor-config record.dat` decodes a local vendor configuration
record and resolves its action list into a 512-byte Glyph matrix. JSON, raw
DEFLATE, zlib and gzip inputs use the bounded profile decoder. This command
performs no device discovery, HID reads, writes, or macro playback.

For an Fn record, choose the target explicitly:

```sh
epomaker preview-vendor-config record.dat --target 'Fn Windows'
epomaker preview-vendor-config record.dat --target 'Fn Mac'
```

`fn: true` does not identify an OS. A normal record requires `Main`, which is the
default. The record must identify model 3059 in `deviceType.id` and contain an
explicit `value` array. A missing or null array is rejected instead of being
treated as a factory reset. An explicit empty array has the vendor full-writer
meaning: the **normal default matrix**, even when targeting Fn. It is not an
OS-specific Fn factory configuration.

The command resolves `original` and `index` through the normal Glyph matrix.
A repeated key identity (such as either Return or Backspace occurrence) requires
an explicit index. Unknown identities, invalid occurrences, malformed actions,
and two actions targeting the same slot are errors. The vendor may silently
ignore an unknown key or overwrite repeated actions; this inspector rejects
those cases so its result is unambiguous.

The JSON report contains the target, matrix hex, changed physical slots, final
macro slot references and action indices that contain a `macro` field. Macro
field presence is not proof of a valid or complete payload. Extra record metadata
is ignored for matrix calculation, and the input object is not modified.
Pass `--include-macros` to validate embedded `ConfigMacro` event/delay pairs
and include normalized Linux events plus a 256-byte payload for each referenced
slot. Explicit empty macros are valid; missing payloads, invalid timing and
conflicting payloads for one slot are errors. Identical payloads sharing a slot
are reported once. Mouse motion uses Linux's unambiguous long-delay encoding.
`unresolved_macro_slots` identifies bindings without converted payloads,
including opaque four-byte macro bindings. `macros_converted` indicates that
conversion was requested, not that every reference has a payload.

The report has its own `epomaker-glyph-vendor-preview` format and
`write_ready: false`; it is not a device snapshot accepted by restore.

The shared byte codec can encode functions used by other models. The preview does
not establish Glyph feature applicability, firmware acceptance, or physical
behavior for those actions. It does not allocate macro slots, retain cloud metadata, or transfer
display/lighting assets. Conversion preserves existing slot IDs; it does not
prove that those slots are free in other profiles.
A complete importer must handle those dependencies before device application.

Implementation: `src/epomaker_driver/vendor_config.py`,
`src/epomaker_driver/vendor_actions.py`, `src/epomaker_driver/vendor_macros.py`, and `src/epomaker_driver/cli.py`.
Source evidence: [full-writer audit](releases/glyph-full-writer-audit.md) and
[action tables](releases/vendor-action-tables.md).

## Plan and import a configuration

Create an offline allocation plan using a previously captured Glyph snapshot:

```sh
epomaker plan-vendor-import vendor.dat --snapshot glyph-backup.json --target Main --profile 1
```

The planner reserves macro IDs referenced by every other normal and Fn OS layer.
It assigns each imported macro a distinct available ID in the vendor app's
0–49 range, in action order, and rewrites its binding. Existing imported slot
IDs are informational; records without a slot ID can also be imported.
Each macro must carry its complete event payload. Opaque macro bindings are
rejected, even if their ID happens to match an allocated macro. Exhaustion is
reported before any write. Unreferenced device macro bytes may be replaced;
the recovery copy retains all 256 slots.

Apply the original vendor record to an explicitly selected device:

```sh
epomaker --device /dev/hidrawN import-vendor-config vendor.dat --target Main --profile 1 --backup before-import.json
```

Replace `/dev/hidrawN` with the path shown by discovery. For Fn use
`--target 'Fn Windows'` or `--target 'Fn Mac'` and profile 0. The importer
captures fresh device state and calculates allocation again; it does not accept
a potentially stale offline plan as authorization to overwrite slots. It saves
a new, private recovery snapshot before the first write, verifies each macro,
then writes and verifies only the selected matrix. An existing backup path
prevents writes. A failure reports the recovery path and possible partial
changes; it does not silently retry or restore over the failure.

This imports one key configuration and its macros. It does not switch the
active profile or OS, import all child profiles, or change lighting and display
assets. Empty records retain the full-writer normal-baseline behavior described
above. Physical Glyph behavior remains unverified.

Implementation: `src/epomaker_driver/vendor_import.py` and
`src/epomaker_driver/vendor_apply.py`; recovery format: `docs/snapshots.md`.

## Graphical import

In **Keymap → Import vendor configuration**, choose a local file and select
**Preview import** while connected to Glyph. The selected layer and Main
profile determine the destination. Review the macro allocation, then select
**Apply preview to keyboard**. The result shows the saved recovery path and
refreshes the displayed keymap.

The API retains only the latest preview, binds its token to the decoded record
and target, and consumes the token on an apply attempt. Disconnecting clears it.
Apply captures device state again and rejects changed allocation before saving
a recovery copy or writing. A failed or stale preview must be repeated.
Files use the same bounded decoder as the CLI; they are processed locally.
