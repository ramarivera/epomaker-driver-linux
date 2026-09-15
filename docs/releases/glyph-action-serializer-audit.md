# Glyph action serializer audit

This audit traces EPOMAKER Driver v4 3.2.22 vendor profile actions into the
Glyph 3059 512 byte key matrices. Offsets are zero based UTF-8 byte offsets in
the raw minified bundle. The bundle was inspected as data only; no vendor
binary was executed.

## Evidence

| Platform | Bundle | Size | SHA-256 | Relevant offsets |
| --- | --- | ---: | --- | --- |
| Windows | `resources/app/dist/js/index.feaf50e4.js` | 2,556,505 | `72fb76b3c19e013d81e450d5245bc62bb5a275fcf6623530a5a652b9c7182be5` | Glyph catalog 896,115; `matrixToConfigs` 1,888,306; `configToMatrix` 1,890,070; reset normal defaults 1,897,320 and Fn defaults 1,898,022; normal write 1,914,276; Fn write 1,917,483 |

The catalog entry at byte 896,115 identifies model `3059`, name
`yc3123_hf_kf107_3m_oled_1k_rgb_kb_soc_v100`, display name `Epomaker Glyph`,
VID `12625`, PID `20482`, three normal layers, and
`fnSysLayer:{win:1,mac:1}`. It also marks `noMagneticSwitch:true` and
`isYC3123:true`. The repository's `src/epomaker_driver/data/glyph-matrices.json`
contains 512 bytes for each of `defaultMatrix`, `defaultFnMatrix`, and
`defaultFnMacMatrix`.

## Action object vocabulary

The vendor's profile `configs` array uses these objects. `original` is the
default matrix key identity, and `index` disambiguates repeated identities.
Fields not listed here are not needed by the four byte serializer and should
be retained when preserving an opaque action.

| `type` | Object fields used | Four byte result |
| --- | --- | --- |
| `combo` | `skey`, `key`, `key2` | If `key <= 255`: `[0,skey,key,key2]`; otherwise the HID value is expanded to four bytes in big endian order by the vendor helper |
| `forbidden` | none | `[0,0,0,0]` |
| `ConfigUnknown` | `value` (four bytes) | `value` copied verbatim |
| `ConfigFunction` | `value` when present, otherwise vendor function table entry for `key` | Explicit `value` copied verbatim; absent/unknown table entries serialize as `[0,0,0,0]` |
| `ConfigMouse` | `key` | Four bytes looked up in the vendor mouse table |
| `ConfigGamepad` | `key` | Four bytes looked up in the vendor gamepad table |
| `ConfigMacro` | `macroType`, `macroIndex` | `[9, mode, macroIndex, 0]`, where `mode` is `0` for `repeat_times`, `1` for `on_off`, and `2` for `touch_repeat`; missing `macroIndex` throws in the vendor writer |
| `ConfigSnap` | `number`, `keyCode` | `[22,number,keyCode,0]` |
| `ConfigMDS` | `number`, `keyCode` | `[23,number,keyCode,0]` |
| `ConfigMT` | `keyCode`, `keyCode2`, `time` | `[24,keyCode,keyCode2,time/10]` |
| `ConfigControlRecoil` | `method`, `gunIndex` | `[22,4,gunIndex,0]` for `normal`, `[22,6,gunIndex,0]` for `switch_keep`, `[22,7,gunIndex,0]` otherwise |

The inverse parser at byte 1,888,306 confirms additional classifications:
`[0,0,1,0]` is `ConfigUnknown`; `[0,0,3,0]` is skipped as a reserved
disabled value; first byte `9` is a macro; `1` is mouse; `21` is gamepad;
first byte `11` is the firepower function with the complete four bytes in
`value`; first byte `22` with second byte 4, 6, or 7 is recoil; other `22`
and `23` values are Snap/MDS; and `24` is MT with `time = byte[3] * 10`.
Unrecognized four byte values become `ConfigUnknown` and retain `value`.
The parser also recognizes vendor function values through its internal
function table, but the table itself is not a stable public schema; unknown
values must remain opaque.

These are branches of a shared serializer, not evidence that every action is
exposed by Glyph. In particular, its magnetic-switch gate remains disabled;
Snap/MDS and other model-specific actions must not become Glyph controls merely
because this generic conversion table can encode them.

## `original`/`index` to physical slot

The serializer does not use `original` as a direct byte offset. At byte
1,888,306, `matrixToConfigs(default, current)` walks the current matrix in
four-byte groups (`s = 0,4,...,508`). For a changed group it sets:

```text
original = matrixToHid(default[s:s+4])
index = count(previous positions p < s where
             default[p:p+4] == default[s:s+4])
```

Thus `index` is a zero-based occurrence count among equal default four-byte
identities. To resolve an action for writing, scan the 128 default slots for
the tuple represented by `original`, select its `index`-th occurrence, and
use that slot number as the Glyph command's physical slot. The command layer
then writes the serialized action to the slot; see the [Glyph protocol
reference](../glyph-protocol.md). Duplicate keys, hidden positions and knob
entries are therefore preserved. A UI key position or HID usage number alone
is insufficient.

`matrixToHid` uses `[0,0,low,0]` as the compact HID form (`low`), otherwise it
interprets the four bytes through JavaScript signed 32-bit shifts/OR, with
mouse-table aliases taking precedence (byte 1,888,155). The combo writer uses
`[0,skey,key,key2]` for keys at most 255; for larger keys it calls helper `jv`
(byte 197,235), which splits the integer through bit masks and shifts. Its first
shift is signed, and values above 0xffffffff produce zeros. A strict adapter
must validate the range and eventual byte coercion rather than copying malformed
JavaScript-number behavior.

## Profiles, defaults, reset and Fn

The interchange record's `value` is one selected profile's `configs` array.
`configValuesForAllSonProfiles` is an outer list of config arrays; the vendor
share path strips each profile's labels before storing it (the extraction is
around byte 1,846,251). The local write path at byte 1,504,944 applies only
the selected `value` to the current normal profile (`profile` matching the
current layer and `sonProfile === 0`), or to the current Fn profile when
`fn:true`. It does not apply the outer list as a batch. For normal records it
also rebuilds generic magnetic state from `magnetismModes`; that path is
inapplicable to Glyph because its catalog explicitly disables magnetic
switches.

Factory/reset initialization at bytes 1,897,320 and 1,921,266 derives normal
defaults with `matrixToConfigs(defaultMatrix, defaultMatrix)`, which returns
an empty action list because unchanged slots are omitted. It creates one
normal `configs` record per layer with `sonProfile:0`; for models with
magnetic support it would create additional son profiles, but Glyph's
`noMagneticSwitch` gate selects one. Empty/zero config arrays are used for
those extra son profiles on supported magnetic models. Fn defaults are made
separately from `defaultFnMatrix` and `defaultFnMacMatrix`, and one record is
created for every configured Fn system and layer.

Fn records are keyed internally by `(profile, sonProfile, fnSys)`; the Glyph
catalog provides one Fn layer for each of `win` and `mac`. The Fn reader calls
`getFnKeyConfig(layer, fnSys)` (byte 1,895,866), and the Fn writer calls
`setFnKeyConfig` with the selected `fnSys` (byte 1,917,483); the single-key
path uses `setFnKeyConfigSimple` at 1,915,395. The reset code
calls `matrixToConfigs(defaultMatrix, defaultFnMatrix)` and
`matrixToConfigs(defaultMatrix, defaultFnMacMatrix)` (bytes 1,898,022 and
1,898,071); this is significant: `original`/`index` remain based on the normal
`defaultMatrix` identity baseline while the Fn matrix supplies the resulting
action bytes. `fn:true` alone is not enough to choose the OS mapping: a Linux
adapter must choose an explicit target system. The share record's unlabelled
outer Fn arrays drop `fnSys`, so they cannot safely reconstruct Windows versus
macOS after interchange.

## Adapter conclusion

The evidence supports a vendor-action adapter for Glyph 3059 for the directly
specified byte forms and opaque preservation path, provided it validates the
model and resolves `(original,index)` against the normal `defaultMatrix`
identity baseline. Mouse, gamepad, and named-function actions additionally
depend on vendor lookup tables (`An`, `Bm`, and the internal function map), so
their names cannot be claimed portable without migrating those tables. The
adapter must reject ambiguous duplicate resolution, missing macro indices,
unknown named functions without a four-byte `value`, and Fn records lacking an
explicit OS mapping. An empty normal action list represents normal defaults.
Fn defaults are differences between the normal identity matrix and the selected
Fn default matrix, so they are not generally empty lists. The full device
writer’s behavior for absent entries still needs tracing before implementing
replacement of a complete imported layer. Do not treat the cloud record's `value` as a
512-byte matrix, and do not infer a physical slot from `original` alone.
