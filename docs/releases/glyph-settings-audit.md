# Glyph settings audit

Baseline: [source installer manifest](../source-releases.json), Windows/macOS
v4 3.2.22. This audit covers model 3059 settings applicability; physical results
remain unverified.

The extracted Windows `dist/js/index.feaf50e4.js` and macOS
`dist/js/index.5af2e057.js` both contain the Glyph model object starting at UTF-8 byte offset
896115 (`id:3059` begins at 896116). It declares three profiles, Windows/Mac Fn layers, Bluetooth
and receiver sleep timers, and no magnetic switches. Both ordinary sleep timers
allow 0–64800 seconds; deep timers allow 10–64800 seconds.

Neither Glyph object has `other.deBounce`. The vendor `supportDebounce` predicate
requires this property: Windows UTF-8 byte offset 1868660, macOS 1877472.
Adjacent models explicitly declare the property. Configurable debounce is therefore
excluded from Glyph vendor feature parity. The Linux settings UI no longer exposes debounce. Glyph status and new snapshots
leave it null; the setter rejects Glyph. Older numeric snapshot values are validated
and ignored on restore with an explicit limitation. This corrects applicability;
it does not add a Glyph feature or establish hardware verification.

The Glyph lighting layouts contain 22 main and six side effects. Functional
metadata already resides in
[`glyph-lighting-capabilities.json`](../../src/epomaker_driver/data/glyph-lighting-capabilities.json).
The graphical lighting controls now use this metadata for effect-specific visibility,
option bounds and translated option labels. Music and screen-color host processing now have explicit Linux capture and
USB streaming workflows; see [live lighting](../live-lighting.md). Their native
visual equivalence and physical behavior remain unverified. See
[the protocol crosswalk](../glyph-protocol.md) and
[the provisional inventory](glyph-v1-features.md).

No vendor code or binary is included in this audit. Offsets refer to the extracted
files from the pinned installer baseline, not JavaScript character indices or
generated pretty-printed copies. The Windows index SHA-256 is
`72fb76b3c19e013d81e450d5245bc62bb5a275fcf6623530a5a652b9c7182be5`;
the macOS index SHA-256 is
`06c91320e6e5b0249fa9f80f055aa5e19099aa5762402cf7098ef8752a832286`.


## Glyph keyboard-option wire layout

The Glyph YC3123 methods differ from the generic shared `LED` state structure.
Do not infer packed bit flags from that generic state or from another device
family. Windows `17dc9c62.js` and macOS `623d2d52.js` contain byte-identical
`setKBOption` / `getKBOption` sections, starting at 30549 / 30851. Their chunk
hashes are recorded in [the full-writer audit](glyph-full-writer-audit.md).

| Command/reply byte | YC3123 meaning |
| --- | --- |
| 0 | Set `09` / get `89` opcode |
| 1 | System selector: Windows 0, Mac 1, iOS 2, Android 3 |
| 2 | Fn index |
| 3 | Accidental-trigger prevention boolean (`防误触开关`) |
| 4 | RT stability divided by 25 on write; read maps values above 5 to zero |
| 5 | WASD/arrow swap, exactly 1 means enabled |
| 6 | Not assigned by the vendor setter |
| 7 | Header checksum |

These are protocol fields, not proof of Glyph controls. Glyph's catalog has only
Windows/Mac Fn systems and disables magnetic switches. Linux exposes Windows/Mac
system selection and WASD swap, while preserving bytes 2–4 and 6 during edits.
The existing `tests/test_device.py::test_options_preserve_fields_and_verify`
checks those fields with nonzero simulator values, both system choices, swap
readback and failed-write detection. Snapshot restore also retains raw options.

Automatic OS selection uses a separate command pair: `17` writes an enabled
boolean at byte 1; `97` reads it. The corresponding vendor methods begin at
35636 / 35800 in both platform YC3123 chunks. Linux implements this separately
from manual system selection. Physical OS switching and automatic detection
remain unverified. Renderer control applicability is a separate audit from this
byte map.


### Renderer evidence limit

The index bundles' `getOther` / change-detection path reads and writes
`autoOsen` (Windows read value at 1942194, setter argument at 1942897;
macOS 1951006 / 1951709). These are state-management handlers, not sufficient
proof that a Glyph-visible form renders an automatic-OS control.

Similarly, the shared `LED` object contains names such as `keyboardMode`,
`keyboardLockControl` and `winKeyLockControl`. The legacy options implementation
in Windows `0175ea1e.js` uses a packed format, while the Glyph YC3123 methods
above use separate bytes. Shared field names must not substitute for model and
renderer-path tracing. The current audit does not establish additional Glyph
switches or justify excluding unresolved controls from release acceptance.
