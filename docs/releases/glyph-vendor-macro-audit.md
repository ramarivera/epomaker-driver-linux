# Glyph vendor macro payload audit

This audit traces how the Glyph/YC3123 Windows bundle creates, stores, hydrates,
serializes, and allocates `ConfigMacro` records. Offsets are zero-based UTF-8
byte offsets in the raw minified files, verified with `read_bytes().find()` on
the unique declaration strings. No vendor code was executed and no network
path was used.

## Sources

| File | Size | SHA-256 | Relevant declarations |
| --- | ---: | --- | --- |
| `resources/app/dist/js/index.feaf50e4.js` | 2,556,505 | `72fb76b3c19e013d81e450d5245bc62bb5a275fcf6623530a5a652b9c7182be5` | `addConfig(e){` 1,497,025; `macroEventToByte=` 488,512; `saveConfig=` 1,503,861; `writeConfig=` 1,504,942; `___存储按键信息=` 1,893,631; `___配置修改=` 1,915,754; `___fn配置修改=` 1,917,052 |
| `resources/app/dist/js/17dc9c62.js` (YC3123 writer) | 38,628 | `eb9f34119b3467a209723f43d8d468a69e3bfa7f9ad45c0d27a37d66d22ccc68` | `matrixToConfigValues=async` 14,030; `buffToMacroEvents=` 14,697; `getMacro=async` 14,420; `setMacro=async` 17,681; `_setMacro=async` 17,274 |

## Local Config record shape and round trip

The keymap editor creates a macro action with these fields (index 1,497,025
and the `ConfigMacro` constructor occurrence at 1,497,943):

```json
{
  "original": 4,
  "type": "ConfigMacro",
  "macro": [{"type":"keyboard","value":4,"action":"down"}, {"type":"delay","value":50}],
  "macroType": "repeat_times",
  "repeatCount": 1,
  "index": 0
}
```

The actual event objects use `type`, `value`, and `action` for keyboard and
mouse button events, and `type`, `dx`, `dy` for motion. The editor
converts its UI event list with `uiMacroEventListToMacroList`; `repeatCount` is
the selected loop time and `macroType` is `repeat_times`, `on_off`, or
`touch_repeat`. New actions initially have `macroIndex` undefined.

`saveConfig` (1,503,861) JSON serializes the complete envelope and compresses
it. The envelope's `value` is the action list, so embedded `macro` and
`repeatCount` fields survive in a Local Config record. `writeConfig` (1,504,942)
decompresses/parses the envelope and assigns `y.configs = o.value ?? []` to the
current normal or Fn record. It does not fetch macro payloads from the cloud or
from the device during this import operation. The optional envelope field
`fn` chooses `fnConfigs`; `magnetismModes` is separate.

Device reads take the reverse route. `matrixToConfigValues=async` (14,030)
first converts the 512 byte key matrix into `ConfigMacro` records with
`macro:[]`, `repeatCount:0`, and `macroIndex` from matrix bytes `[9, mode,
macroIndex, 0]`. For every such record it calls `getMacro(macroIndex)`
(14,420), then replaces the empty fields with `macroEvents` and `repeatCount`.
`getMacro` requests up to four 64 byte chunks using command `FEA_CMD_GET_MACRO`
and stops at a zero chunk. Thus a device-derived record has the same embedded
payload fields as a Local Config action; a matrix-only interchange must not
discard them.

## Exact macro payload encoding

`setMacro` (17,681) allocates a 256 byte buffer. Bytes 0–1 are
`repeatCount & 255` and `repeatCount >> 8` (little endian). It then consumes
`macro` in pairs: each first event must be a non-delay keyboard or mouse event,
and the second must be a `delay` event. The shared `macroEventToByte` declaration
(index 488,512 in the main bundle) supplies the event bytes:

| Event | Bytes | Timing |
| --- | --- | --- |
| keyboard | `[hidValue, marker]` | `marker = delay` for key-up, `delay + 128` for key-down when delay ≤127; for longer delay, marker is `0`/`128` followed by little endian 16 bit delay |
| mouse button | `[buttonCode, marker]` with vendor button codes from `An[button][2]` | same marker and long-delay rule |
| mouse move | `[249, delay, dx, dy]` for delay ≤127; `[249, 0, dx, dy, delayLo, delayHi]` otherwise | `dx`/`dy` are signed bytes |

The writer copies each resulting event byte sequence at the next buffer offset
and sends the 256 bytes through `_setMacro` (17,274). `_setMacro` uses command
`FEA_CMD_SET_MACRO`, slot byte 1 = `macroIndex`, and up to five 56 byte chunks.
It counts nonzero chunks, sets chunk byte 2 to the chunk number, byte 3 to 56,
byte 4 to 1 only on the final chunk, and zero pads the final payload. An all
zero payload sends zero chunks. The sender counts nonzero groups and sends the
first `n` groups, which can omit later nonzero data when an earlier group is
all zero; Linux should serialize contiguous groups or
reject such a raw layout. The slot is therefore fixed at 256 bytes, with a
maximum of 254 bytes available after the repeat count (subject to event
boundaries).

The YC3123 full writers call `setMacro(action, macroIndex)` before the matrix:
`setKeyConfig` at byte 18,395 in `17dc9c62.js`, and `setFnKeyConfig` at byte
34,786. The simple key writer also calls it for a `ConfigMacro` at byte 16,257.
The matrix action is `[9, mode, macroIndex, 0]`; mode is 0=`repeat_times`,
1=`on_off`, 2=`touch_repeat`. A macro payload write and its key binding are
separate operations, so a Linux importer must allocate/write slots before or
alongside matrix serialization.

## Allocation and collisions

The app reserves 50 macro slots, IDs 0 through 49 (`maxMacro=50`, byte
1,900,841). `___getAllMacroIDList` (1,900,853) scans both normal `configs` and
Fn `fnConfigs` and collects every defined `macroIndex`; IDs are global across
those collections. Full normal allocation in `___配置修改` (1,915,754) collects
the current actions, gathers IDs from all other profiles, then assigns each
current macro the first unused integer, in action order. Fn allocation in
`___fn配置修改` (1,917,052) uses the same helper to reserve IDs across normal and Fn collections,
with the exclusion caveat below. It
rejects when current plus other macro records exceed 50, and aborts if no free
ID remains.

The editor's ordinary `addConfig` (1,497,025) removes the first existing record
whose `original` matches, without comparing `index`, then appends the new
record. This can erase a duplicate physical binding when records share an
`original` but differ by occurrence. Other update paths use
`original && index`; the YC3123 resolver itself uses `findIndexInDefaultMatrix(
original,index)` and preserves duplicate identities. An importer must therefore
keep `(original,index)` distinct and reject an out-of-range index.

If an imported list contains two records targeting the same `(original,index)`
or two records carrying the same `macroIndex`, the vendor full writer does not
deduplicate them: it iterates records and calls `setMacro` in order. The later
payload overwrites the same device slot, while the matrix contains only the
last effective four-byte binding at that physical position. Linux should reject
these collisions (or report an explicit last-write policy) instead of silently
assuming that two payloads can share one slot. Likewise, an imported
`macroIndex` outside 0–49 or a collision with another normal/Fn record cannot be
resolved by the vendor allocator without remapping.

## Linux mapping

Linux `macros.encode` already matches the vendor's 256 byte layout for keyboard,
mouse button, and explicit long-delay motion. Preserve the vendor event pairs,
`repeatCount`, `macroType`, and `macroIndex`; map vendor button codes through
the semantic names rather than treating them as HID usages. Do not infer an
absent payload from `[9, mode, macroIndex, 0]`: that four-byte matrix record
identifies a slot, while the slot's event data is a separate required payload.
An explicitly present `macro:[]` can represent an empty macro and must not be
conflated with a missing `macro` field. Validate `repeatCount` and the full
event-pair shape before deciding whether a payload is usable. Vendor zero-delay
encoding and compact motion remain ambiguous on readback; Linux uses the
unambiguous long-delay motion form and rejects zero-delay events, as documented
in `docs/macros.md`. The action byte codec alone does not convert these events.

The allocation helper excludes collections by their array position, and the
Fn selection does not explicitly filter `fnSys` in the inspected full-update
path. A Linux allocator must validate actual normal/Fn target identity and
reserve occupied slots from device state, rather than assuming the vendor
array-index shortcut always protects the other OS bank.


## Implemented conversion

`src/epomaker_driver/vendor_macros.py` converts explicit event/delay pairs to
Linux events and delegates payload validation to `macros.encode`. The offline
preview's `--include-macros` option includes these payloads, rejects conflicting
slot contents, and reports unresolved references. Preview conversion retains existing slot IDs. The separate
`vendor_import` planner reserves IDs used by other layers and assigns fresh
slots; `vendor_apply` plans from a live snapshot and saves recovery before
verified macro and matrix writes. Hardware validation remains open. See [preview usage](../vendor-config-preview.md).
