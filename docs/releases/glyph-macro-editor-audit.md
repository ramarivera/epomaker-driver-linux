# Glyph macro editor audit

Baseline: [pinned Windows/macOS installers](../source-releases.json), driver
v4 3.2.22. Evidence below uses byte offsets in Windows `fd19495c.js` and macOS
`918febcc.js`; the reviewed sections match on both platforms. This is a partial
control audit, not physical verification or a closed inventory.

| Workflow | Vendor evidence | Linux status |
| --- | --- | --- |
| Named macro collection | 16000–17800: selection, rename, rejection of blank names, deletion and `ALL_MACROS` persistence. 22500–23300: generated names, UUID and a new entry with events and playback metadata. | Missing. The numeric device-slot editor holds a single draft in memory. A persistent named collection is required for Glyph v1. |
| Playback metadata | 26500–27680: count bounded to 1–65535, toggle, and while-held selection. 32500–32900: Save invokes `saveMacro`. | Repeat editing exists; count/toggle/held binding selection lives in Keymap. The complete library-to-assignment workflow needs verification. Separate placement alone does not prove a missing device capability. |
| Insert and capture one action | 29396–30942: an editing placeholder accepts a keyboard/mouse action; a coordinate entry is also insertable. | Numeric usage/button/coordinate editing exists, as does sequence recording. One-action capture remains missing. |
| Local/cloud collection interaction | 19300–19750: page mount passes local entries through IOT DB helpers and invokes synchronization. 18500–19072: sharing has SDK/company/login conditions. | Local persistence is required. Helper behavior and shipped Glyph service gates need further tracing before deciding cloud applicability; these calls alone do not prove a mandatory network dependency. |

The reviewed page does not show a JSON file import/export control. This limited
observation does **not** establish that Linux JSON is compatible with all vendor
file workflows, or that Linux functionality is a superset. Broader configuration
and service paths remain to be audited.

Device macro slots, app-local named entries, and key playback bindings are distinct.
The future library must preserve names and playback preferences without pretending
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
