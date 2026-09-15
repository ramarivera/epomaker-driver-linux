# Glyph backup and vendor configuration workflow audit

The inspected EPOMAKER Driver v4 3.2.22 “Local Config” screen manages a local
configuration database and cloud sharing. No portable backup-file controls were
found in this screen or its traced record codec. The evidence below is from the exact Windows and macOS bundles listed
in [the source manifest](../source-releases.json). Offsets are zero-based
UTF-8 byte offsets in the raw minified files; they are not JavaScript line
numbers and the vendor code is paraphrased here.

## Evidence

| Platform | Evidence file | Bytes | SHA-256 | Relevant offsets |
| --- | --- | ---: | --- | --- |
| Windows | `resources/app/dist/js/index.feaf50e4.js` | 2,556,505 | `72fb76b3c19e013d81e450d5245bc62bb5a275fcf6623530a5a652b9c7182be5` | DB namespaces 1,149,342; config codec 1,502,459; config record class 1,500,641; save/write path 1,503,863 |
| Windows | `resources/app/dist/js/6a8dfe90.js` | 6,386 | `f6a37264f77f77fd21c7fa36d156ce645ecc0d2b7a0b5a0ebea08a52c161de41` | Local Config screen and controls, file start (0–6,385) |
| macOS | `Contents/Resources/app/dist/js/index.5af2e057.js` | 2,565,198 | `06c91320e6e5b0249fa9f80f055aa5e19099aa5762402cf7098ef8752a832286` | DB namespaces 1,154,783; config codec 1,511,271; config record class 1,509,453 (bundled as `Fy`); save path 1,512,675 |
| macOS | `Contents/Resources/app/dist/js/5360a4c7.js` | 6,386 | `f3b3b5c0c18bed71cafd9005707d5688044988b87a56186b95d6d96246cc53c7` | Local Config screen and controls, file start (0–6,385) |

The macOS class is renamed by the bundle minifier (`Fy` rather than Windows'
`Ty`); its exact declaration starts at offset 1,509,453. `Sp` at 1,511,567
is the separate macro record class, not the configuration class.

## What the vendor configuration contains

The shared record shape is an object with these named fields: `localId`,
optional `serverId`, `name`, optional `dpi`, optional `reportRate`, `value`,
`configValuesForAllSonProfiles`, `magnetismModes`, `deviceType`, `fn`,
`isShared`, `hasUpload`, `needDelete`, `user`, and `category`. The database row
around it adds `id`, `title`, `describe`, `screen_type` (`config` for a
keyboard, `config_mouse` for a mouse), `create_at`, `company`, compressed
`data`, `width`, and `height` (Windows index offset 1,503,863; macOS index
offset 1,512,675).

For a Glyph keyboard, `value` is the selected profile's key configuration
array; `configValuesForAllSonProfiles` preserves the profile/son-profile
arrays. A Fn record sets `fn` and carries the selected Fn-system values. The
write path applies `value` to the current profile and can also reconstruct
magnetic-switch settings from `magnetismModes`; this is generic shared driver
machinery and does not make magnetic controls applicable to Glyph. The record
also carries `deviceType` identity and optional `reportRate`, but no display
pixels, GIF frames, still-image bytes, lighting picture bytes, or macro event
stream.

The exact codec is: stringify the complete record as UTF-8 JSON, then apply
raw DEFLATE (`deflateRaw`), storing the resulting bytes. The decoder selects zlib-wrapped DEFLATE for the header `78 9c`, gzip for
`1f 8b`, and raw DEFLATE otherwise (Windows helper `xl`, byte 1,500,507).
If decompression fails or returns no bytes, the record parser falls back to
UTF-8 JSON. Records produced by this path use raw DEFLATE. There is no schema-version
integer, magic header, checksum, or documented portable file container in the
configuration record itself (Windows index offsets 1,500,641 and 1,502,459;
macOS index offsets 1,511,567 and 1,511,271).

The Local Config UI enumerates `config_new` rows, permits a title up to 20
characters, and exposes **Write**, **Delete**, **Rename**, and (when enabled)
**Share**. It does not expose Export or Import, and it has no file picker or
download path. Windows chunk `6a8dfe90.js` and macOS chunk `5360a4c7.js` each
show the same four-column table and the same operation menu. Share uploads the
compressed record through the vendor service; it is not a local backup file.

## Separate display and lighting stores

The bundle declares independent database namespaces: `SCREEN`,
`SCREEN_IMAGE_BUFFER`, `IMG_SHARE`, `CONFIG_NEW`, `CONFIG_NEW_BUFFER`, `LIGHT`,
`LIGHT_IMAGE_BUFFER`, `MACRO`, and `MACRO_BUFFER` (Windows index offset
1,149,342 onward; macOS index offset 1,154,783 onward). The application state
also keeps screen-picture rows separate from light-picture rows (Windows
offset 1,756,861; macOS offset 1,765,673). This is direct evidence that display
assets are not embedded in a Local Config record. The packaged display
resources and the host display/screen-capture services are likewise separate
from the keyboard configuration database.

The vendor bundle contains image/GIF conversion dependencies and separate
screen/light workflows, but that does not establish that a Local Config export
would include them: no such export exists in the inspected UI or codec path.
The only demonstrated configuration payload is the compressed JSON described
above. Screen images and GIF/raw frame data therefore remain separately
managed assets and must be preserved by a Linux backup integration as source
assets for replay. The keyboard cannot be treated as a readable source of
those pixels; a backup made only from device readback cannot recreate them.

## Applicability to Glyph 3059

This is applicable to Glyph management. The main Windows/macOS model catalog
identifies internal model **3059** as EPOMAKER Glyph (VID 12625, PID 20482),
and the Local Config page filters keyboard records by keyboard `config` type.
The workflow is therefore not an unused generic method that can be dismissed
for v1. It is the vendor's actual profile/configuration management surface for
the connected keyboard. Applicability does not imply every generic field is
meaningful: Glyph's catalog disables magnetic-switch controls, and no vendor
evidence here adds screen pixels to config records.

## Linux backup and restore requirements

1. Keep the existing versioned device snapshot as the authoritative
   device-state backup for readable/manageable fields: identity, profiles and
   Fn/key bindings, lighting settings, macros and other implemented readable fields. Display language, clock state
   and screen contents are not currently captured by this snapshot. Preserve all 256 Glyph macro slots, including unreferenced slots.
2. Add a clearly separate asset manifest/sidecar for each saved Glyph still or
   animation. Retain original source bytes, destination bank/layer, effective
   animation delay, model id 3059, and a content digest. Do not claim that
   device snapshot readback captured screen pixels.
3. Do not promise import/export compatibility with an EPOMAKER “config file”:
   the inspected vendor UI has no such file workflow. A Linux portable backup
   should use a documented Linux schema and may optionally retain the vendor
   raw compressed record only as forensic provenance.
4. Implement the applicable local named-configuration save/write/rename/delete
   workflows. Shared/cloud records require a separate service audit. If sharing compatibility is ever pursued, implement a narrow adapter for
   the record fields above: UTF-8 JSON plus raw DEFLATE, with strict model and
   field validation. Treat `deviceType`, `value`, Fn values, profile arrays and
   `magnetismModes` as untrusted input. Do not infer screen or light assets
   from absent fields.
5. Validate all device state and asset sidecars before starting restoration,
   save recovery copies, then restore through explicit device and asset stages.
   Device writes are not atomic; replay display assets explicitly. Report assets that cannot be replayed or
   whose source bytes are missing; never silently mark a display image as
   restored.

## Reusable current Linux implementation

The independent named key-layer library now implements save, rename, delete,
preview and verified apply; see `src/epomaker_driver/config_library.py` and
`ui/src/config-library.jsx`. It does not yet consume vendor records or represent
all vendor subprofile/sharing metadata. `profiles.decode` accepts bounded JSON,
raw DEFLATE, gzip, and valid zlib wrappers (including zlib headers beyond the
vendor helper’s `78 9c` heuristic). It rejects truncated streams, trailing bytes,
concatenated members, invalid checksums and oversized expansion. Decoding is
separate from model-specific validation and does not authorize device writes.

The existing snapshot capture/validation/restore and recovery-copy path in
`src/epomaker_driver/snapshot.py`, `src/epomaker_driver/server.py`, and
`src/epomaker_driver/cli.py` is reusable for the device-state half. The
versioned schemas and Glyph model gates already provide the right place to add
an asset manifest. `src/epomaker_driver/display_library.py` and
`docs/glyph-display-assets.md` already provide an independent, validated
portable asset object (`epomaker-glyph-display-asset`, version 1, model 3059),
original base64 source retention, still/animation timing, atomic persistence,
and authenticated import/export endpoints. Integrate that library by reference
or add its manifest entries to a future snapshot schema; do not merge it into
the vendor `config_new` interpretation.

## Unreadable or unproven state

The following cannot currently be recovered from a keyboard snapshot alone:
the pixels in the five display banks, the original image/GIF source bytes when
Linux has not retained them, and any host-side vendor library metadata outside
the device protocol. The inspected vendor bundles also do not establish a
portable config-file version, checksum, or screen-asset embedding rule. These
are explicit limitations to carry into the G11 backup acceptance record.
