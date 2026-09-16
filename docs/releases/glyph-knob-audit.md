# Glyph knob assignments

Baseline: [installer manifest](../source-releases.json), Windows/macOS v4 3.2.22.
Offsets below are UTF-8 bytes in the extracted renderer index bundles. Windows
SHA-256: `72fb76b3c19e013d81e450d5245bc62bb5a275fcf6623530a5a652b9c7182be5`;
macOS: `06c91320e6e5b0249fa9f80f055aa5e19099aa5762402cf7098ef8752a832286`.

The Glyph model object begins at byte 896115 in both bundles. Its
`other.knobKeyCodes` identifies three inputs of the knob, rather than three knobs:

| Input | Matrix slot | Factory action |
| --- | ---: | --- |
| AudioVolumeDown | 109 | `03 00 ea 00` |
| MediaPlayPause | 53 | `03 00 cd 00` |
| AudioVolumeUp | 108 | `03 00 e9 00` |

Slot correspondence comes from the normal Glyph default matrix and
[layout crosswalk](glyph-pattern-key-slots.json). It is source-derived, not a
physical rotation/press test.

The shared renderer reads the current model's `other.knobKeyCodes`. Consequently
these predicates apply to Glyph, even though their code is shared with other
models:

- Macro assignment tests membership in those knob codes and rejects the selected
  macro type `按下播放` (while held), returning before constructing its assignment.
  The membership expression starts at Windows 1793246 / macOS 1802058; the macro
  type comparison starts at 1793304 / 1802116.
- Keyboard hover excludes knob inputs when the selected layer is Fn:
  Windows 2320581 / macOS 2329392.
- Keyboard selection applies the same Fn exclusion:
  Windows 2325559 / macOS 2334370.

Linux individual key assignment now rejects Fn knob edits and held macro bindings
(`09 02 index 00`) before a configuration write. The editor disables the three
knob controls on both Fn layers, disables held playback for knobs, and explains
why a retained knob selection or raw held action cannot be applied. Count and
toggle macros remain assignable. Ordinary keys retain Fn and held playback.

Implementation: `src/epomaker_driver/device.py` and `ui/src/keymap.jsx`.
Regression evidence: `tests/test_glyph_knobs.py` and `ui/tests/glyph-knobs.spec.js`.
The latter covers all three inputs, both Fn tabs, raw input, and simulated
readback. No physical command round trip has been performed.

This closes the individual-assignment restriction gap only. Existing full-matrix
backup/restore and vendor/local configuration imports remain byte-preserving;
their treatment of changed knob actions needs a separate audit. The new guard
is not a claim that all configuration entry points enforce these restrictions,
or that firmware cannot contain or execute a binding hidden by the vendor UI.
