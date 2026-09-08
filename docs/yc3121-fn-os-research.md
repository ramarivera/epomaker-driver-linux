# Older YC3121 Fn and OS addressing findings

Applies to RT100 (1379) and Dynatab75X-UK (1723), whose model loaders inherit
CommonKbYc500. Sources are the installer pair in
[source-releases.json](source-releases.json); module identity comparisons are
recorded in [yc3121.md](yc3121.md). These are static protocol findings, not
hardware observations. Fn layer 0 reads and writes are now implemented as described
in [yc3121.md](yc3121.md); manual OS controls remain unimplemented.

## Fn matrices

The older parent (`ef0a2b57.js` on macOS / `17f7eda9.js` on Windows) reads Fn
matrices with `[90, layer, page]`, eight raw 64-byte pages. Its `_getFnKeyMatrix`
accepts a second argument but never uses it. The public `getFnKeyConfig` forwards
that unused argument. CommonKbYc500's single Fn write (`7b0fe1d1.js` /
`0175ea1e.js`) is `[15, layer, slot]`, with four action bytes at offsets 8–11.
It accepts only the action and layer arguments. Both use checksum byte 7.

The shared vendor UI passes an OS string to both methods: the read loop iterates
`fnSysLayer` keys and calls `getFnKeyConfig(layer, system)` (macOS main bundle
113075–113101), while the single-key edit calls
`setFnKeyConfigSimple(action, layer, currentFnSystem)` (113547–113549).
Consequently the same layer/page or layer/slot produces identical command bytes
for Windows and Mac on this older class. Catalog declarations of one Fn layer
per OS do not prove independently addressable storage. A Linux implementation
must not claim independent Windows and Mac Fn matrices from these methods alone.

The inherited bulk Fn writer uses opcode `10`, declared length 504 (`f8 01`),
and nine 56-byte chunks. The single-slot opcode avoids dropping the final eight
readable bytes, as with normal matrices. The model classes declare a
`defaultFnMACMatrix` property, whereas the parent declares `defaultFnMacMatrix`.
The single-slot restore path explicitly uses `defaultFnMatrix`. Case-sensitive
property names and the ignored OS selector need to remain visible in any
future default-restoration design.

The implementation now exposes Fn layer 0 addressed by these packets, preserves
unknown slots, and reads back changes. Do not label a second
independent Mac bank without evidence. Verify hardware behavior across manual
OS changes before claiming an OS-specific mapping.

## Older option flags

`getOldKBOption(profile)` sends `[86, profile]`; `setOldKBOption(profile, options)`
sends `[06, profile, flags, fnFlag, powerSave]`. Both methods live in the same
CommonKbYc500 module pair. The decoder reads `system` from bit 1 of reply byte 2
and returns the string `mac` or `win`. The setter calls `Number(options.system)`
and shifts it left by 2. JavaScript converts either string to NaN, then bitwise
coercion produces zero. Even a numeric value would target a different bit from
the reader. Therefore this setter does not establish a reliable manual OS
selection encoding.

Other flags in byte 2: Windows-key lock bit 0, WASD/arrow swap bit 3, main LED off
bit 4, side LED off bit 5, keyboard mode bit 6, keyboard lock bit 7. Reply byte 3
bit 0 reports Fn-matrix selection; byte 4 reports power saving. The vendor UI's
`checkLed` calls this setter with the complete previously decoded object when
LED-off changes (macOS main bundle 115439–115447), potentially clearing OS bits.
A future implementation should preserve unrelated raw fields when toggling a
known flag instead of reproducing that conversion bug.

Automatic OS selection (`17`/`97`) is a separate, already migrated command.
These manual-option ambiguities do not invalidate that implementation.
