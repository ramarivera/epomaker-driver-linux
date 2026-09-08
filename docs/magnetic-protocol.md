# Modern magnetic-key protocol

This is a pure codec description derived from the shared modern base in the
macOS `623d2d52.js` and Windows `17dc9c62.js` bundles. Their entire contents
match after imported chunk filenames are normalized. This codec performs no
device access. The [HE60 backend](he60-lite-research.md) now uses its bulk
read and decoding functions; magnetic-setting writes remain codec-only.

The multi-key read command is packetized as `e5 field 01 page` and the
corresponding write command as `65 field 00 key-index commit 00 00 00`, with
the payload beginning at byte 8. Both are padded to the repository's 64-byte
packet shape and checksum byte 7. Read responses are accumulated as complete
64-byte reports; the base does not remove an eight-byte header. Unknown bytes
are retained by the codec.

Travel values are multiplied by 10 for versions below `0x0300`, 100 from
`0x0300` through `0x04ff`, and 200 from `0x0500` onward. RF version takes
precedence over USB version when nonzero; an absent version uses multiplier 10. Top dead
zone fields are available only when either version is at least `0x0400`.

Field IDs confirmed in both bundles are travel 0, lift travel 1, rapid-trigger
press/lift 2/3, dynamic travel 4, MT time 5, dead zone 6, mode 7, trigger
modes 8, snap binding 9, and top dead zone 251. Travel fields are little-endian
16-bit values; MT time, mode, snap, axis, and top-dead-zone fields are one byte;
top-dead-zone values use the travel multiplier before being stored. Trigger
modes are four bytes. Bulk field 10 is read-only and consists of four 128-byte
stage arrays; field 8 is the four-byte simple-write form. Travel conversion
truncates after multiplication, matching the vendor's bitwise conversion; it
does not round to the nearest integer. Out-of-range values are rejected
instead of reproducing the vendor's integer wraparound.

| Bulk read field | Pages of 64 bytes | Slot representation |
| --- | --- | --- |
| 0, 1, 2, 3, 4, 6 | 4 | 128 little-endian uint16 values |
| 5, 7, 9, 251, 252 | 2 | 128 one-byte values |
| 10 | 8 | Four stage arrays of 128 bytes each |

Read field 10 at stage `g`, slot `p`, is byte `g * 128 + p`.
The byte-level codec preserves unknown mode/axis values; it does not yet map
them to user-facing magnetic modes or switch types. Calibration and model
integration remain unimplemented and hardware validation is outstanding. The
`write_commands` helper accepts an already-selected set of changed simple
fields and emits the vendor order with only the final command committed; it
does not infer diffs from prior state. Snap pairing and axis-type (252) writes
are separate vendor transactions and are not emitted by that helper.

Evidence locations in the prettified macOS base: version gates 124–139,
bulk reads and field decoding 951–1119, mode encoding 1124–1158,
simple-write packet and sequencing 1338–1463, and paired snap writes
1466–1482. The codec is `src/epomaker_driver/magnetic.py`; version requests
are in `src/epomaker_driver/versions.py`. See also
[HE60 Lite research](he60-lite-research.md) for model-specific constraints.
