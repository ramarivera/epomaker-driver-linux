# Modern magnetic-key protocol

This is a pure codec description derived from the shared modern base in the
macOS `623d2d52.js` and Windows `17dc9c62.js` bundles. Their entire contents
match after imported chunk filenames are normalized. This codec performs no
device access. The [HE60 backend](he60-lite-research.md) now uses its bulk
read, decoding and ordered-write functions for actuation and rapid-trigger
updates and normal/DKS/MT/toggle mode definitions with action bindings. Reciprocal snap pairing and pair removal are integrated by `he_snap.py`.

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

The shared UI applies an old-firmware exception before catalog limits. The
effective version is nonzero RF when available, otherwise USB; a missing version
acts as zero. For effective versions from `0x0001` through `0x02ff`, travel and lift use a
maximum of 4 mm. Bottom dead zone uses a maximum of 4 mm for effective versions
below `0x0300`, including effective version zero. When a rapid
trigger step is missing from the catalog, the UI fallback is 0.1 mm below
`0x0300`, 0.01 mm from `0x0300` through `0x04ff`, and 0.005 mm at `0x0500` or
later. Values must still be representable by the wire multiplier. These gates
are shown in the macOS main UI at lines 107169–107180, 107859, 107796/107828,
and 107677–107702.

Field IDs confirmed in both bundles are travel 0, lift travel 1, rapid-trigger
press/lift 2/3, dynamic travel 4, MT time 5, dead zone 6, mode 7, trigger
modes 8, snap binding 9, and top dead zone 251. Travel fields are little-endian
16-bit values; MT time, mode, snap, axis, and top-dead-zone fields are one byte;
top-dead-zone values use the travel multiplier before being stored. Trigger
modes are four bytes. Bulk field 10 is read-only and consists of four 128-byte
stage arrays; field 8 is the four-byte simple-write form. Travel conversion
truncates fractional wire units after exact decimal multiplication; it
does not round to the nearest integer. Out-of-range values are rejected
instead of reproducing the vendor's integer wraparound.

| Bulk read field | Pages of 64 bytes | Slot representation |
| --- | --- | --- |
| 0, 1, 2, 3, 4, 6 | 4 | 128 little-endian uint16 values |
| 5, 7, 9, 251, 252 | 2 | 128 one-byte values |
| 10 | 8 | Four stage arrays of 128 bytes each |

Read field 10 at stage `g`, slot `p`, is byte `g * 128 + p`.
The byte-level codec preserves unknown mode/axis values. HE60 integrates the
known magnetic modes. [HE68 Lite](ry5088-he68.md) supports model-gated
switch-type selection through separate committed field-252 writes, preserving
other magnetic state and keymaps. [Timed USB calibration](calibration.md) is available; physical validation remains
outstanding. The
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


## Multi-action magnetic modes

A magnetic action is represented jointly by the mode byte and normal keymap
submodes. DKS (`2`) uses four actions at submodes 0–3; MT (`3`) uses hold then
tap actions at submodes 0–1; toggle hold (`4`) and toggle dots (`5`) use one
action at submode 0. The high mode bit independently enables rapid trigger.
Each action retains the existing four-byte key-binding representation.

The application writes changed actions first through single-key `0a` packets,
with the active profile and action index as submode. Only the final action
packet carries its action-group commit. It then writes the magnetic mode and
parameters through `65`: mode field 7 first, followed by changed simple fields,
with a separate final magnetic-group commit. These groups are not an atomic
transaction; readback must verify both keymap and magnetic state.

DKS stores four two-bit trigger cells in each action's trigger byte:
`cell0 | cell1 << 2 | cell2 << 4 | cell3 << 6`. Four action bytes are written as
field 8, while readback places each at `action_index * 128 + key_slot` in bulk
field 10. Dynamic travel is field 4. MT's duration is field 5, encoded in units
of 10 milliseconds. Wire capacity alone does not establish the UI's limits.

The macOS main bundle's pretty lines 112500–112538 establish the action order
and trigger packing; 113580–113608 reconstruct actions from submodes, and
113685–113701 establish action-before-parameter write order. Single-key reset
is a distinct operation: lines 113717 onward restore the base action and clear
all three extra submodes. Ordinary mode updates must not silently perform that
reset or erase unrelated submode data.

Decimal scaling deliberately avoids the vendor’s binary-floating-point artifact
for valid UI increments (for example, 2.3 × 100 encoding as 229). See the
[precision correction](ry5088-wireless.md) and the raw-baseline regression tests.
