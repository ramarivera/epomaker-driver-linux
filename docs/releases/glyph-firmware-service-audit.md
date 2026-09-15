# Glyph firmware service request and observed result

The Windows main bundle `index.feaf50e4.js` (SHA-256
`72fb76b3c19e013d81e450d5245bc62bb5a275fcf6623530a5a652b9c7182be5`)
contains the following request contract. Offsets are zero-based UTF-8 bytes.
This extends the [image/container audit](glyph-firmware-image-audit.md).

| Declaration | Byte offset | Contract |
| --- | --- | --- |
| `hp` | 1,254,028 | Calls the POST wrapper with an 8-second timeout |
| `getFwVersion` | 1,254,141 | `/get_fw_version`, JSON body `{dev_id: runtimeId}` |
| `qR` | 1,260,662 | `https://api2.rongyuan.tech:3816/api/v2` |
| `gp` | 1,260,706 | `https://api2.rongyuan.tech:3816/download` |
| `_3` | 1,260,966 | POST; success is response JSON `code === 0`, metadata in `data` |
| `su` | 1,261,918 | GET with arraybuffer response |
| `getFirmwareUpgradeListFromServer` | 1,825,366 | Requires USB; passes runtime model ID; requires main image before listing candidates |

The firmware request method adds no session field or explicit authentication
header. The separate bit-image API hostname is not the firmware service.
No credentials were supplied in the following lookup.

## Observed model-3059 lookup

On 2026-09-16, two read-only POST lookups using `{"dev_id":3059}` reached
the traced endpoint and returned **HTTP 500**. The second lookup captured the
16-byte plain-text response **`Record not found`**. No image was downloaded and
no device was queried or put into boot mode.

This is a failed lookup, not an empty update list and not proof that no Glyph
firmware exists. The service's current model mapping, record availability and
any additional server-side requirements remain unresolved. Do not guess another
model ID or flash another keyboard's image to work around this response.

The Linux `firmware-metadata` command and explicit Settings metadata button
implement this exact model-3059 request,
with bounded response size and explicit errors. It does not download the returned
`file_path`, validate an image's identity, or apply updates. The service supplies
no captured successful Glyph record in this investigation. Synthetic client
fixtures establish request/error handling only.

## Version comparison

The selector extracts all ASCII digit runs from each token, concatenates them,
and parses the result in base 16. For example, `v1.0.2` compares as `0x0102`,
not as a semantic version. The first nonempty underscore-separated token refers
to USB regardless of its prefix. Later lowercase `rfv`, `oledv`, `flashv`,
`mledv`, and `nordicv` markers select their component images.

The Linux offline analyzer additionally rejects ambiguous/duplicate tokens,
unknown component names, and values beyond the uint16 fields understood by the
current Glyph version parser. Missing/zero runtime versions remain unavailable;
they do not establish a component update candidate. MLED/Nordic candidates are
marked unsupported because the recovered dispatcher does not implement them.
These conservative differences are visible, not a claim of a byte-for-byte
emulation of all shared updater behavior.

Implementation and tests: `src/epomaker_driver/firmware_service.py`,
`src/epomaker_driver/firmware_versions.py`, `tests/test_firmware_service.py`,
`tests/test_firmware_versions.py`, and `tests/test_firmware_cli.py`.
