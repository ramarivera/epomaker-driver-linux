# Glyph macro editor audit

Baseline: [pinned Windows/macOS installers](../source-releases.json), driver
v4 3.2.22. Evidence below uses byte offsets in Windows `fd19495c.js` and macOS
`918febcc.js`; the reviewed sections match on both platforms. This is a partial
control audit, not physical verification or a closed inventory.

| Workflow | Vendor evidence | Linux status |
| --- | --- | --- |
| Named macro collection | 16000–17800: selection, rename, rejection of blank names, deletion and `ALL_MACROS` persistence. 22500–23300: generated names, UUID and a new entry with events and playback metadata. | Local named creation, rename, update, deletion and disk persistence now exist. Explicit loading preserves the destination slot; device assignment remains separate. |
| Playback metadata | 26500–27680: count bounded to 1–65535, toggle, and while-held selection. 32500–32900: Save invokes `saveMacro`. | Repeat editing exists; count/toggle/held binding selection lives in Keymap. The complete library-to-assignment workflow needs verification. Separate placement alone does not prove a missing device capability. |
| Insert a captured key/button pair | 29200–30950: an editing placeholder accepts a keyboard/mouse press, then appends press/release actions with a delay after each. A coordinate entry is separately insertable. | Numeric editing, sequence recording, captured pair insertion, and event identity replacement now exist. Pair insertion validates capacity; row replacement preserves direction and delay. |
| Local/cloud collection interaction | 19300–19750: page mount passes local entries through IOT DB helpers and invokes synchronization. 18500–19072: sharing has SDK/company/login conditions. | Local persistence is required. Helper behavior and shipped Glyph service gates need further tracing before deciding cloud applicability; these calls alone do not prove a mandatory network dependency. |

The reviewed page does not show a JSON file import/export control. This limited
observation does **not** establish that Linux JSON is compatible with all vendor
file workflows, or that Linux functionality is a superset. Broader configuration
and service paths remain to be audited.

The insertion handlers at bytes 29200–30950 match between the two bundles. A
single captured key or mouse press inserts both down and up, each followed by
50 ms in measured mode or the selected fixed delay. It does not measure how long
that input was held. Coordinate insertion adds an explicit position and delay;
it is not continuous pointer recording. This refines the earlier general
description of a one-action picker and keeps pair insertion separate from editing
the identity of an existing press or release event.

## Explicit mouse motion

The vendor position-row controls clamp each component to -127 through 127
(`fd19495c.js`/`918febcc.js`, around bytes 34657–35919). The shared conversion at
bytes 487900–489350 of `index.feaf50e4.js`/`index.5af2e057.js` maps position X/Y
to `mouse_move` with `dx`/`dy`. This supports interpreting the editor fields as
relative deltas rather than absolute screen positions; firmware behavior still
needs verification.

The same index section emits `F9`, a delay marker, and two signed-byte components.
Short delays use their value as the marker; long delays use marker zero and an
extra little-endian 16-bit delay. The shared decoder in `17dc9c62.js`, bytes
14675–15567, reads signed components but shifts nonzero motion markers right by
one. Thus the vendor encoder's 10 ms short delay is decoded as 5 ms. This is a
source-level asymmetry, not an observed hardware timing result.

Linux retains its explicit long-delay encoding for all motion events and rejects
ambiguous compact-motion decoding. The semantic format allows -128 through 127,
matching signed-byte capacity; -128 is outside the audited vendor UI range and its
physical acceptance remains unverified. Axis orientation, distance, and playback
timing also remain hardware checks. See [macro encoding](../macros.md).

Device macro slots, app-local named entries, and key playback bindings are distinct.
The local library preserves names and playback preferences without pretending
those names are stored in the device's 256-byte macro slot. Loading or saving a
library entry must make its destination slot and assignment behavior clear.

The Linux raw-export control preserves bytes even when semantic decoding fails.
Its filename and slot metadata refer to the original successful load, including
when the destination slot changes during that request. Editing a decoded draft
does not rewrite the raw snapshot. See [macro formats](../macros.md).

Remaining evidence: actual firmware playback and timing, persistence and capacity,
USB/Bluetooth/receiver restrictions, library save/assignment behavior, service
gates, and any vendor configuration-file representation. No vendor source or assets
are included here.
