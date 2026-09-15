# Glyph config interchange audit

This records the value/action representation and cloud share envelope found in EPOMAKER Driver v4 3.2.22. It supplements the [backup workflow audit](glyph-backup-workflow-audit.md). Offsets are zero-based UTF-8 byte offsets in the raw minified files.

## Evidence

| Platform | Bundle | Bytes | SHA-256 | Relevant offsets |
| --- | --- | ---: | --- | --- |
| Windows | `resources/app/dist/js/index.feaf50e4.js` | 2,556,505 | `72fb76b3c19e013d81e450d5245bc62bb5a275fcf6623530a5a652b9c7182be5` | `shareBitImage` 1,155,055; `downloadImageBymd5` 1,155,558; class `Ty` 1,500,641; codec 1,502,459; local save 1,503,863; local write 1,504,944; share construction 1,753,460; local save action extraction 1,846,251 |
| macOS | `Contents/Resources/app/dist/js/index.5af2e057.js` | 2,565,198 | `06c91320e6e5b0249fa9f80f055aa5e19099aa5762402cf7098ef8752a832286` | `shareBitImage` 1,160,496; `downloadImageBymd5` 1,160,999; class `Fy` 1,509,453; codec 1,511,271; local save 1,512,675; local write 1,513,756 |

The macOS minifier renames the Windows `Ty` class to `Fy`.

## Value and profile semantics

The record has `localId`, optional `serverId`, `name`, optional `dpi` and `reportRate`, `value`, `configValuesForAllSonProfiles`, `magnetismModes`, `deviceType`, `fn`, sharing flags, `user`, and `category`. For a keyboard, `value` is the selected profile's vendor action array (`configs`). It is not a 512-byte matrix and is not base64-wrapped. Actions carry fields such as source key (`original`), type, key codes (`skey`, `key`, `key2`), and `index`.

`writeConfig` selects the current profile with `sonProfile === 0` and assigns that profile's `configs` from `value`. For non-Fn records it also rebuilds generic magnetic-switch state from `magnetismModes`; this does not establish magnetic support for Glyph. The inspected config path contains no action to 4-byte matrix conversion. A Linux adapter can preserve vendor actions as opaque validated data, but cannot claim arbitrary action-to-Glyph-512-byte conversion from this evidence.

`configValuesForAllSonProfiles` is an outer list of `configs` arrays for all son profiles of the selected parent profile. The save path constructs it with `configs.filter(profile === selected).map(configs)`, stripping profile and son-profile metadata. Fn records also map `fnConfigs` entries selected by parent profile to arrays, dropping `fnSys` identity as well. Do not assume those unlabelled Fn arrays represent normal son-profile slots. Keep both the outer list and selected `value` as opaque data until their target mapping is established.

Fn records set `fn: true`. The local save path chooses the Fn profile using current profile plus `fnSys` (the Fn OS/system identity), while the separate share-construction path chooses by profile and does not visibly add `fnSys` to the record. There is no dedicated OS field in the record. Require an explicit Linux mapping; do not infer Windows/macOS from `fn: true`.

`deviceType` is built as `{company, id, displayName, name}` from the connected device. The Glyph catalog identifies model 3059. Validate this identity before applying any actions. Width and height are separate envelope metadata derived from device id and are not matrix bytes.

## Compression and share/download envelope

`encodeAndCompressConfig` stores raw DEFLATE of UTF-8 `JSON.stringify(record)` (Windows 1,502,459; macOS 1,511,271). The decoder tries zlib-wrapped DEFLATE for `78 9c`, gzip for `1f 8b`, otherwise raw DEFLATE, then UTF-8 JSON. Shared config uses the same raw-DEFLATE bytes.

Sharing POSTs multipart form data to `/share_bit_image`, with `title`, `description`, `width`, `height`, `screen_type` (derived from `config` for Glyph by helper `o1`), numeric `user_id`, session, company, and an `image` part containing compressed bytes as `application/octet-stream`. At Windows byte 1,260,875, `o1` conditionally returns the type unchanged or appends `:<company>` depending on application flags; this audit does not resolve those flags. The field name does not mean an image file. The common wrapper returns `{errCode, data, response}` without further config normalization.

Discovery uses `/list`, `/list_v2`, `/user_likes`, and `/user_bit_image_list`; payload fetch is GET `/<md5>` through the configured download base URL. `downloadImageBymd5` returns arraybuffer bytes. `downloadSharedConfig_web` copies record fields, sets the current user, generates a new local id, and stores the result locally. No portable file download, filename, base64 envelope, checksum, or schema version is established.

## Adapter boundary

Safe interoperability is limited to validating model identity and fields, preserving action/profile arrays as JSON, raw-DEFLATE codec compatibility, and reproducing multipart names if service sharing is explicitly needed. Applying actions to a 512-byte Glyph matrix, reconstructing Fn OS identity, and carrying display/lighting assets require links not present in this vendor path. Do not infer them from `value`, profile arrays, width/height, or the multipart field named `image`.

The Linux decoder implementation now accepts bounded gzip, zlib and raw-DEFLATE
objects; see `src/epomaker_driver/profiles.py` and `tests/test_profiles.py`. This
is codec compatibility only. The next required trace is from profile `configs`
actions through the Glyph-specific key writer into each four-byte binding.

The subsequent [action serializer audit](glyph-action-serializer-audit.md)
identifies per-action byte formulas and the normal-matrix identity used for Fn
keys. Its remaining lookup-table and full-writer constraints still apply before
claiming general record-to-matrix interchange.

The [full-writer audit](glyph-full-writer-audit.md) now establishes the normal
default baseline for full normal and Fn conversion. It also identifies embedded
macro payload consumption, which a matrix-only adapter would omit.
