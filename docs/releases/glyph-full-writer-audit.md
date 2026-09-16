# Glyph full writer audit

This audit traces the complete imported-config write path for EPOMAKER Driver
v4 3.2.22 and the YC3123 keyboard writer used by Glyph 3059. Offsets below are
zero-based **UTF-8 byte offsets** in the raw minified files; they were checked
with `read_bytes().find()` and byte slices, rather than character offsets. No
vendor code was executed.

## Evidence

| File | Size | SHA-256 | Relevant byte offsets |
| --- | ---: | --- | --- |
| `resources/app/dist/js/index.feaf50e4.js` | 2,556,505 | `72fb76b3c19e013d81e450d5245bc62bb5a275fcf6623530a5a652b9c7182be5` | `writeConfig` 1,504,944; normal full call 1,914,276; Fn full call 1,917,483; Glyph catalog 896,115 |
| `resources/app/dist/js/17dc9c62.js` (YC3123 writer) | 38,628 | `eb9f34119b3467a209723f43d8d468a69e3bfa7f9ad45c0d27a37d66d22ccc68` | `setKeyConfigSimple` 15,859; `_configsToMatrix` 16,459; `_changeAllConfig` 16,649; `_setKeyConfig` 18,007; `setKeyConfig` 18,395; Fn decode/read 33,077/33,208; `setFnKeyConfigSimple` 33,592; `_setFnKeyConfig` 34,402; `setFnKeyConfig` 34,786 |

The catalog entry at index byte 896,115 identifies Glyph as model 3059,
`isYC3123:true`, `noMagneticSwitch:true`, three normal layers, and one Fn
layer for each of `win` and `mac`. The `17dc9c62.js` byte slices contain the
YC3123 command implementation used by this family.

## What an absent imported action list does

At index byte 1,504,944, local `writeConfig` selects the current normal or Fn
record and assigns `y.configs = o.value ?? []`. It then schedules either
`配置修改` or `fn配置修改`. The normal full path at byte 1,914,276 passes its
selected `configs` to `dev.setKeyConfig`; the Fn path at byte 1,917,483 passes
its selected `configs` to `dev.setFnKeyConfig`.

The YC3123 full normal writer (`setKeyConfig`, byte 18,395) calls
`_configsToMatrix` and that starts with `this.defaultMatrix` (the implementation
at bytes 16,459–17,050). It applies each supplied action, then computes `ceil(512 / 56)` and sends ten chunks in `_setKeyConfig`
(byte 18,007): nine full chunks and eight meaningful bytes in the last, padded
to 56 bytes. The final normal header length is 8. Consequently `value` absent, null, or an empty array writes a complete
copy of `defaultMatrix`; it does not leave the device untouched and does not
mean a zero-filled layer. This matches the serializer audit’s empty-list
meaning for normal factory defaults.

The Fn full writer (`setFnKeyConfig`, byte 34,786) also calls the same
`_configsToMatrix`, whose baseline is **the normal `defaultMatrix`**, then sends
the resulting 512 bytes through `_setFnKeyConfig`. Thus an absent Fn `value`
writes normal default bindings into the Fn layer. It does not construct the
Fn layer from `defaultFnMatrix` or `defaultFnMacMatrix`. The Fn defaults only
enter the specialized single-key path described below. An importer must either
materialize the intended Fn baseline as actions or reject an absent Fn value;
silently passing `[]` reproduces this vendor quirk, which is usually not the
desired semantic for a Linux interchange format.

## Physical resolution and duplicate keys

The YC3123 full conversion records each action as `{changeArr, orginHid,
index}` and `_changeAllConfig` calls `_changeMatrix` for each record. The
`_changeMatrix` loop (bytes 16,805–17,420) scans the 128 default four-byte
slots. It compares the HID identity and counts matching prior slots; when
`index` is present it selects the requested occurrence. Therefore full writes
preserve duplicate identities and map `original,index` to a physical slot.
Unknown identities are skipped (the baseline byte group remains unchanged).

This differs from the older generic base implementation in `17f7eda9.js`:
its `configsToMatrix` (byte slice containing `findIndexInDefaultMatrix(s.original)`)
omits `s.index` and always resolves the first duplicate. The Glyph adapter must
use the YC3123 implementation’s indexed resolver, and should reject an
out-of-range occurrence rather than silently selecting another duplicate.

The single-key normal command at byte 15,859 likewise resolves
`findIndexInDefaultMatrix(t.original,t.index)`, emits command `FEA_CMD_SET_KEYMATRIX`
with the selected physical index, and writes the four converted bytes at packet
offsets 8–11. Full and simple writes therefore agree on indexed physical
resolution in the YC3123 path.

## Fn writer packet and baseline quirks

The Fn system is decoded by `_解码fnSys` at byte 33,077 (`win` → 0, `mac` → 1,
`ios` → 2, `android` → 3, unknown → 0). `_setFnKeyConfig` emits ten packets
(`s=0..9`) at bytes 34,402–35,000. Header bytes are command `FEA_CMD_SET_FN`,
decoded system, layer, and `255`; chunks 0–8 carry 56 bytes and chunk 9 carries
the remaining eight bytes padded to 56, but its header length is 0, not 8.
The final marker is set only on chunk 9. The
writer always sends all 512 bytes, including unchanged baseline groups.

`setFnKeyConfigSimple` (byte 33,592) uses the indexed physical slot and the
selected system’s Fn default matrix only for the identity-preserving combo
case (`original == key == key2 == skey`); it returns a config reconstructed
from that Fn default group. Other actions use `configToMatrix` and preserve
macro side effects. This special-case behavior must not be generalized to the
full writer: full Fn writes use normal `defaultMatrix` as their conversion
baseline.

## Importer requirements

For a complete imported normal layer, initialize from the Glyph normal
`defaultMatrix`, resolve every `(original,index)` against that same 128-slot
identity list, apply actions in record order, and write all 512 bytes. Treat
missing normal `value` as an explicit request for the normal factory baseline
only if that is the format’s documented policy.

For Fn records, require an explicit target system (`win` or `mac`) and do not
use `fn:true` or the share envelope alone to infer it. A missing Fn `value`
must not be mistaken for the OS-specific Fn factory matrix: the vendor full
writer would send normal `defaultMatrix` instead. Preserve duplicate indices,
reject invalid indices and unknown identities, and keep macro allocation and
macro writes separate from the 512-byte matrix conversion.

## Macro payloads are a separate required write

Both full writers iterate `ConfigMacro` actions and call `setMacro(action,
macroIndex)` before writing the matrix. The method consumes `action.macro` and
`repeatCount`; these fields can therefore occur inside the record’s `value`
action objects. This corrects the earlier inference that Local Config records
categorically exclude macro event data. Which read/share paths populate those
arrays still needs tracing; a record may instead carry an empty list. A complete
importer must validate and preserve any embedded payload, establish allocation
and slot-collision behavior, and report absent payloads. Converting only the
four-byte binding is not equivalent to the vendor’s full configuration write.

The [vendor configuration preview](../vendor-config-preview.md) resolves explicit
action arrays using this baseline. The separate `src/epomaker_driver/vendor_apply.py`
workflow now allocates and writes embedded macros, saves a recovery snapshot,
and applies/read-verifies the selected matrix. Preview alone performs no writes.
Physical importer parity remains unverified.

## macOS comparison and knob records

The macOS YC3123 chunk `dist/js/623d2d52.js` has 38,628 bytes and SHA-256
`e4f4ca92f999856242fae8ac6d527bf930a44223d03a5e9665993718f965a6c6`.
The conversion range [16459,17420), normal-writer range [18007,19300), and
Fn-writer range [34402,35700) are byte-identical to the Windows chunk. The
public normal and Fn entry points are 18395 and 34786 on both platforms.

Neither full conversion nor these writers checks `knobKeyCodes` or rejects held
macro mode. The normal identity/occurrence resolver applies knob actions like
other supplied actions, and both writers write each embedded `ConfigMacro`
payload before the matrix. The individual editor exclusions are therefore not
bulk-format constraints. See [knob evidence and preservation tests](glyph-knob-audit.md).
Linux full Fn restoration uses changed-slot writes rather than the vendor's ten
full chunks; equal simulated readback does not establish wire equivalence.
