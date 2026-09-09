# Glyph settings audit

Baseline: [source installer manifest](../source-releases.json), Windows/macOS
v4 3.2.22. This audit covers model 3059 settings applicability; physical results
remain unverified.

The extracted Windows `dist/js/index.feaf50e4.js` and macOS
`dist/js/index.5af2e057.js` both contain the Glyph model object at byte offset
877750 (line 365). It declares three profiles, Windows/Mac Fn layers, Bluetooth
and receiver sleep timers, and no magnetic switches. Both ordinary sleep timers
allow 0–64800 seconds; deep timers allow 10–64800 seconds.

Neither Glyph object has `other.deBounce`. The vendor `supportDebounce` predicate
requires this property: Windows byte offset 1780105, macOS 1788917 (line 365).
Adjacent models explicitly declare the property. Configurable debounce is therefore
excluded from Glyph vendor feature parity. The current Linux settings UI, generic
status/setter and snapshot restoration still include debounce; removing that
incorrect exposure while handling older snapshots is pending work, not completion.

The Glyph lighting layouts contain 22 main and six side effects. Functional
metadata already resides in
[`glyph-lighting-capabilities.json`](../../src/epomaker_driver/data/glyph-lighting-capabilities.json).
The current graphical lighting controls are generic: effect-specific visibility,
option bounds and option labels need reconciliation against that metadata. See
[the protocol crosswalk](../glyph-protocol.md) and
[the provisional inventory](glyph-v1-features.md).

No vendor code or binary is included in this audit. Offsets refer to the extracted
files from the pinned installer baseline, not generated pretty-printed copies.
