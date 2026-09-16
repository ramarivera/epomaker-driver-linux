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
