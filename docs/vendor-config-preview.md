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
The report has its own `epomaker-glyph-vendor-preview` format and
`write_ready: false`; it is not a device snapshot accepted by restore.

The shared byte codec can encode functions used by other models. The preview does
not establish Glyph feature applicability, firmware acceptance, or physical
behavior for those actions. It also does not convert embedded macro events,
allocate macro slots, retain cloud metadata, or transfer display/lighting assets.
A complete importer must handle those dependencies before device application.

Implementation: `src/epomaker_driver/vendor_config.py`,
`src/epomaker_driver/vendor_actions.py`, and `src/epomaker_driver/cli.py`.
Source evidence: [full-writer audit](releases/glyph-full-writer-audit.md) and
[action tables](releases/vendor-action-tables.md).
